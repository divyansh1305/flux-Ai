"""A tiny stand-in for Turso's HTTP API (POST /v2/pipeline), backed by a local SQLite file.

Used by the tests to run Kitna through flux.remote_db exactly as on Vercel. It follows the protocol's
rules that matter: each baton is its own server connection, autocommit unless BEGIN, typed values,
foreign keys OFF until the client turns them on (like a fresh SQLite connection).
"""
import base64
import json
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _py(v):
    t = v.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(v["value"])
    if t == "float":
        return float(v["value"])
    if t == "blob":
        return base64.b64decode(v["base64"])
    return v["value"]


def _wire(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, bytes):
        return {"type": "blob", "base64": base64.b64encode(v).decode()}
    return {"type": "text", "value": v}


class FakeLibsql:
    def __init__(self, path, token="test-token"):
        self.path, self.token = path, token
        self.streams = {}
        self.requests = 0
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        for c in self.streams.values():
            c.close()

    def _handler(self):
        server = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                if self.path != "/v2/pipeline" or self.headers.get("Authorization") != f"Bearer {server.token}":
                    self.send_response(401); self.end_headers(); return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                server.requests += 1
                baton = body.get("baton")
                if baton and baton not in server.streams:
                    self.send_response(400); self.end_headers(); self.wfile.write(b'{"message":"stream not found"}'); return
                conn = server.streams.pop(baton, None) if baton else None
                if conn is None:
                    conn = sqlite3.connect(server.path, isolation_level=None, check_same_thread=False, timeout=10)
                results, closed = [], False
                for req in body["requests"]:
                    if req["type"] == "close":
                        closed = True
                        results.append({"type": "ok", "response": {"type": "close"}})
                        continue
                    st = req["stmt"]
                    args = [_py(a) for a in st.get("args", [])]
                    try:
                        cur = conn.execute(st["sql"], args)
                        rows = cur.fetchall()
                        cols = [{"name": d[0], "decltype": None} for d in (cur.description or [])]
                        results.append({"type": "ok", "response": {"type": "execute", "result": {
                            "cols": cols, "rows": [[_wire(v) for v in r] for r in rows],
                            "affected_row_count": max(cur.rowcount, 0),
                            "last_insert_rowid": str(cur.lastrowid) if cur.lastrowid else None}}})
                    except sqlite3.Error as e:
                        results.append({"type": "error", "error": {"message": str(e)}})
                new_baton = None
                if closed:
                    conn.close()
                else:
                    new_baton = secrets.token_hex(8)
                    server.streams[new_baton] = conn
                out = json.dumps({"baton": new_baton, "base_url": None, "results": results}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        return H
