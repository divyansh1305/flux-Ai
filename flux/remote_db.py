"""A small sqlite3-compatible connection to a remote libSQL database (Turso) over its HTTP API.

Kitna's SQL is plain SQLite, and Turso runs SQLite, so the queries stay exactly the same. Only the
connection changes: on Vercel there is no lasting disk, so the data lives in Turso instead of a file.

It behaves like Python's sqlite3 where Kitna relies on it:
  * conn.execute(sql, params) -> cursor with fetchone / fetchall / iteration / lastrowid / rowcount
  * rows can be read by name or by position, and dict(row) works (like sqlite3.Row)
  * the first INSERT / UPDATE / DELETE starts a transaction; commit() / rollback() end it
  * conn.total_changes goes up on every write (used to cache dashboard numbers within a request)
One HTTP "stream" (a server-side connection, identified by a baton) is kept per Flask request, so
transactions and PRAGMA foreign_keys (needed for ON DELETE CASCADE) work as they do locally.

Protocol: https://docs.turso.tech/sdk/http/reference  (POST {url}/v2/pipeline)
"""
import base64
import re
import sqlite3

import requests

_session = requests.Session()
_WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|REPLACE)\b", re.I)
_TX = re.compile(r"^\s*(BEGIN|COMMIT|END|ROLLBACK)\b", re.I)
# PRAGMAs that only make sense for a local file; the server manages these itself.
_LOCAL_PRAGMA = re.compile(r"^\s*PRAGMA\s+(journal_mode|busy_timeout|synchronous|wal_checkpoint)\b", re.I)


class Row(tuple):
    """A result row: row[0], row["name"], dict(row), row.keys(): like sqlite3.Row."""

    def __new__(cls, values, cols, index):
        r = super().__new__(cls, values)
        r._cols, r._index = cols, index
        return r

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return tuple.__getitem__(self, self._index[key])
            except KeyError:
                raise IndexError(f"No item with that key: {key}") from None
        return tuple.__getitem__(self, key)

    def keys(self):
        return list(self._cols)


class Cursor:
    def __init__(self, cols=(), rows=(), lastrowid=None, rowcount=-1):
        index = {c: i for i, c in enumerate(cols)}
        self.description = tuple((c, None, None, None, None, None, None) for c in cols) or None
        self._rows = [Row(r, tuple(cols), index) for r in rows]
        self._pos = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        if self._pos >= len(self._rows):
            return None
        self._pos += 1
        return self._rows[self._pos - 1]

    def fetchall(self):
        out, self._pos = self._rows[self._pos:], len(self._rows)
        return out

    def fetchmany(self, size=1):
        out = self._rows[self._pos:self._pos + size]
        self._pos += len(out)
        return out

    def __iter__(self):
        while True:
            r = self.fetchone()
            if r is None:
                return
            yield r


def _arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"type": "blob", "base64": base64.b64encode(bytes(v)).decode()}
    return {"type": "text", "value": str(v)}


def _value(v):
    t = v.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(v["value"])
    if t == "float":
        return float(v["value"])
    if t == "blob":
        return base64.b64decode(v.get("base64", ""))
    return v.get("value")


def _stmt(sql, params):
    s = {"sql": sql}
    if params:
        if isinstance(params, dict):
            s["named_args"] = [{"name": k, "value": _arg(v)} for k, v in params.items()]
        else:
            s["args"] = [_arg(v) for v in params]
    return s


def _error(err):
    msg = (err or {}).get("message", "database error")
    if "constraint" in msg.lower():
        return sqlite3.IntegrityError(msg)
    return sqlite3.OperationalError(msg)


def split_script(script):
    """Split a .sql file into statements (handles ';' inside quotes and BEGIN…END trigger bodies)."""
    out, buf, quote, depth = [], [], None, 0
    i, n = 0, len(script)
    while i < n:
        ch = script[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == "-" and script.startswith("--", i):
            j = script.find("\n", i)
            i = n if j < 0 else j
            continue
        elif ch == ";" and depth == 0:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
        else:
            buf.append(ch)
            word = re.match(r"[A-Za-z]+", script[i:]) if (i == 0 or not script[i - 1].isalnum()) else None
            if word:
                w = word.group(0).upper()
                if w == "BEGIN" and re.search(r"\bTRIGGER\b", "".join(buf), re.I):
                    depth += 1
                elif w == "END" and depth:
                    depth -= 1
        i += 1
    s = "".join(buf).strip()
    if s:
        out.append(s)
    return out


class RemoteConnection:
    row_factory = None   # accepted for compatibility; rows always behave like sqlite3.Row

    def __init__(self, url, token, timeout=15):
        url = url.strip()
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        self.url = url.rstrip("/")
        self._base = self.url
        self.token = token
        self.timeout = timeout
        self._baton = None
        self.in_transaction = False
        self.total_changes = 0

    # ─── transport ────────────────────────────────────────────
    def _pipeline(self, reqs, retry=True):
        body = {"baton": self._baton, "requests": reqs}
        try:
            r = _session.post(f"{self._base}/v2/pipeline", json=body, timeout=self.timeout,
                              headers={"Authorization": f"Bearer {self.token}"} if self.token else {})
        except requests.RequestException as e:
            raise sqlite3.OperationalError(f"database unreachable: {e}") from None
        if r.status_code != 200:
            # The server forgot our stream (idle for >10 s). Safe to reopen if no transaction was open.
            if retry and self._baton and not self.in_transaction and r.status_code in (400, 404):
                self._baton, self._base = None, self.url
                return self._pipeline(self._open() + reqs, retry=False)[len(self._open()):]
            raise sqlite3.OperationalError(f"database HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        self._baton = data.get("baton")
        if data.get("base_url"):
            self._base = data["base_url"].rstrip("/")
        return data.get("results", [])

    @staticmethod
    def _open():
        # Every new server connection needs foreign keys on, or ON DELETE CASCADE does nothing.
        return [{"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys = ON"}}]

    def _run(self, stmts):
        """Run statements in this connection's stream; returns the result of the last one."""
        reqs = ([] if self._baton else self._open()) + [{"type": "execute", "stmt": s} for s in stmts]
        results = self._pipeline(reqs)
        last = None
        for res in results:
            if res.get("type") == "error":
                raise _error(res.get("error"))
            last = (res.get("response") or {}).get("result")
        return last

    # ─── sqlite3-style API ────────────────────────────────────
    def execute(self, sql, params=()):
        if _LOCAL_PRAGMA.match(sql):
            return Cursor()
        tx = _TX.match(sql)
        if tx:
            word = tx.group(1).upper()
            if word == "BEGIN":
                if not self.in_transaction:
                    self._run([{"sql": "BEGIN"}])
                    self.in_transaction = True
            elif word in ("COMMIT", "END"):
                self.commit()
            else:
                self.rollback()
            return Cursor()
        stmts = []
        is_write = bool(_WRITE.match(sql))
        if is_write and not self.in_transaction:
            stmts.append({"sql": "BEGIN"})   # like sqlite3: writes wait for commit()
        stmts.append(_stmt(sql, params))
        res = self._run(stmts) or {}
        if is_write:
            self.in_transaction = True
            self.total_changes += max(1, int(res.get("affected_row_count") or 0))
        cols = [c.get("name") for c in res.get("cols", [])]
        rows = [[_value(v) for v in row] for row in res.get("rows", [])]
        lid = res.get("last_insert_rowid")
        return Cursor(cols, rows, int(lid) if lid not in (None, "") else None,
                      int(res.get("affected_row_count") or 0) if is_write else -1)

    def executemany(self, sql, seq):
        cur = Cursor()
        for params in seq:
            cur = self.execute(sql, params)
        return cur

    def executescript(self, script):
        self.commit()
        stmts = [s for s in split_script(script) if not _LOCAL_PRAGMA.match(s)]
        if stmts:
            self._run([{"sql": s} for s in stmts])
        return Cursor()

    def commit(self):
        if self.in_transaction:
            self.in_transaction = False
            self._run([{"sql": "COMMIT"}])

    def rollback(self):
        if self.in_transaction:
            self.in_transaction = False
            self._run([{"sql": "ROLLBACK"}])

    def close(self):
        if self._baton:
            try:
                reqs = ([{"type": "execute", "stmt": {"sql": "ROLLBACK"}}] if self.in_transaction else []) + [{"type": "close"}]
                self._pipeline(reqs, retry=False)
            except Exception:  # noqa: BLE001  closing must never break a response
                pass
        self._baton, self.in_transaction = None, False
