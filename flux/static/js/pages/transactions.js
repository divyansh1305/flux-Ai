(function () {
  const { el, icon, api, download, err, pageHead, txRow, deleteTx, addTransactionModal, onRefresh, meta } = window.Flux;

  // First page of Activity starts loading in parallel with the sign-in check.
  let early = api("/api/transactions?page=1&size=30", { allow401: true }).catch(() => null);

  async function render(main) {
    const m = await meta();
    const state = { page: 1, kind: "", category: "", q: "", from: "", to: "" };
    const list = el("div", { class: "tx-list" });
    const more = el("button", { class: "btn block", style: { marginTop: "12px" } }, "Load more");
    const kindSeg = el("div", { class: "seg" });
    [["", "All"], ["expense", "Expenses"], ["income", "Income"], ["saving", "Savings"]].forEach(([k, label]) => {
      const b = el("button", { type: "button", class: k === "" ? "on" : "" }, label);
      b.onclick = () => { state.kind = k; [...kindSeg.children].forEach((c) => (c.className = "")); b.className = "on"; reload(); };
      kindSeg.appendChild(b);
    });
    const cat = el("select", { class: "input", style: { width: "auto" }, "aria-label": "Category filter" },
      el("option", { value: "" }, "All categories"), [...m.expense_categories, ...m.income_categories].map((c) => el("option", { value: c }, c)));
    cat.onchange = () => { state.category = cat.value; reload(); };
    const q = el("input", { class: "input", placeholder: "Search notes…", style: { maxWidth: "220px" }, "aria-label": "Search" });
    let t;
    q.oninput = () => { clearTimeout(t); t = setTimeout(() => { state.q = q.value.trim(); reload(); }, 300); };
    const from = el("input", { class: "input", type: "date", style: { width: "auto" }, "aria-label": "From date" });
    const to = el("input", { class: "input", type: "date", style: { width: "auto" }, "aria-label": "To date" });
    from.onchange = () => { state.from = from.value; reload(); };
    to.onchange = () => { state.to = to.value; reload(); };

    const qs = (extra = {}) => {
      const p = new URLSearchParams();
      Object.entries({ ...state, ...extra }).forEach(([k, v]) => { if (v) p.set(k, v); });
      return p.toString();
    };
    async function load(append) {
      try {
        const query = qs({ size: 30 });
        const show = (r) => {
          const rows = r.items.map((x) => txRow(x, deleteTx));
          if (append) list.append(...rows); else list.replaceChildren(...rows);
          if (!append && !r.items.length) list.replaceChildren(el("div", { class: "empty" }, el("b", null, "No transactions found"), "Try different filters, or add one."));
          more.classList.toggle("hidden", !r.has_more);
        };
        const pre = query === "page=1&size=30" ? early : null;
        early = null;
        if (!append && query === "page=1&size=30") await window.Flux.live("/api/transactions?" + query, show, pre);
        else show(await api("/api/transactions?" + query));
      } catch (e) { err(e); }
    }
    function reload() { state.page = 1; load(false); }
    more.onclick = () => { state.page += 1; load(true); };
    onRefresh(reload);

    const exp = (fmt) => download("/api/transactions/export?" + qs({ format: fmt, page: "" }), `flux-transactions.${fmt}`).catch(err);
    main.replaceChildren(
      pageHead("Transactions", "Every rupee in and out.",
        el("button", { class: "btn", onclick: () => exp("csv") }, icon("download"), "CSV"),
        el("button", { class: "btn", onclick: () => exp("pdf") }, icon("download"), "PDF"),
        el("button", { class: "btn primary", onclick: () => addTransactionModal() }, icon("plus"), "Add")),
      el("div", { class: "card" },
        el("div", { class: "row wrap", style: { marginBottom: "12px" } }, kindSeg, cat, q, from, el("span", { class: "faint" }, "→"), to),
        list, more));
    reload();
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
