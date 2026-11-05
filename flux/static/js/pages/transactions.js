(function () {
  const { el, icon, api, download, err, pageHead, txRow, deleteTx, addTransactionModal, onRefresh, meta } = window.Kitna;

  // First page of Activity starts loading in parallel with the sign-in check.
  let early = api("/api/transactions?page=1&size=30", { allow401: true }).catch(() => null);

  async function render(main) {
    const m = await meta();
    const state = { page: 1, kind: "", category: "", q: "", from: "", to: "" };
    const list = el("div", { class: "tx-list" }, ...window.Kitna.skeleton(5).children);
    const more = el("button", { class: "btn block", style: { marginTop: "12px" } }, "Load more");
    const kindSeg = el("div", { class: "seg full" });
    [["", "All"], ["expense", "Money out"], ["income", "Money in"]].forEach(([k, label]) => {
      const b = el("button", { type: "button", class: k === "" ? "on" : "" }, label);
      b.onclick = () => { state.kind = k; [...kindSeg.children].forEach((c) => (c.className = "")); b.className = "on"; reload(); };
      kindSeg.appendChild(b);
    });
    const cat = el("select", { class: "input", "aria-label": "Category filter" },
      el("option", { value: "" }, "All categories"), [...m.expense_categories, ...m.income_categories].map((c) => el("option", { value: c }, c)));
    cat.onchange = () => { state.category = cat.value; reload(); markFilter(); };
    const q = el("input", { class: "input", type: "search", placeholder: "Search", "aria-label": "Search" });
    let t;
    q.oninput = () => { clearTimeout(t); t = setTimeout(() => { state.q = q.value.trim(); reload(); }, 300); };
    const from = el("input", { class: "input", type: "date", "aria-label": "From date" });
    const to = el("input", { class: "input", type: "date", "aria-label": "To date" });
    from.onchange = () => { state.from = from.value; reload(); markFilter(); };
    to.onchange = () => { state.to = to.value; reload(); markFilter(); };
    const filters = el("div", { class: "filters", hidden: true }, cat,
      el("div", { class: "row", style: { gap: "8px" } }, from, el("span", { class: "faint" }, "to"), to));
    const filterBtn = el("button", { class: "icon-link", type: "button", title: "Filters", "aria-label": "Filters", "aria-expanded": "false",
      onclick: () => { filters.hidden = !filters.hidden; filterBtn.setAttribute("aria-expanded", String(!filters.hidden)); } }, icon("sliders"));
    const markFilter = () => filterBtn.classList.toggle("active", !!(state.category || state.from || state.to));

    const qs = (extra = {}) => {
      const p = new URLSearchParams();
      Object.entries({ ...state, ...extra }).forEach(([k, v]) => { if (v) p.set(k, v); });
      return p.toString();
    };
    async function load(append) {
      try {
        const query = qs({ size: 30 });
        const show = (r) => {
          // Day headings, like a bank statement: Today, Yesterday, 4 Nov…
          const rows = [];
          let lastDay = append ? list.dataset.lastDay : null;
          r.items.forEach((x) => {
            if (x.date !== lastDay) { rows.push(el("div", { class: "day-head" }, window.Kitna.dateFmt(x.date))); lastDay = x.date; }
            rows.push(txRow(x, deleteTx));
          });
          list.dataset.lastDay = lastDay || "";
          if (append) list.append(...rows); else list.replaceChildren(...rows);
          if (!append && !r.items.length) list.replaceChildren(el("div", { class: "empty" }, el("b", null, "No transactions found"), "Try different filters, or add one."));
          more.classList.toggle("hidden", !r.has_more);
        };
        const pre = query === "page=1&size=30" ? early : null;
        early = null;
        if (!append && query === "page=1&size=30") await window.Kitna.live("/api/transactions?" + query, show, pre);
        else show(await api("/api/transactions?" + query));
      } catch (e) { err(e); }
    }
    function reload() { state.page = 1; load(false); }
    more.onclick = () => { state.page += 1; load(true); };
    onRefresh(reload);

    const exp = (fmt) => download("/api/transactions/export?" + qs({ format: fmt, page: "" }), `kitna-activity.${fmt}`).catch(err);
    const dl = el("details", { class: "menu-pop" }, el("summary", { class: "btn", "aria-label": "Download" }, icon("download")),
      el("div", { class: "menu-pop-in" },
        el("button", { type: "button", class: "menu-item plain", onclick: () => exp("csv") }, "Download CSV"),
        el("button", { type: "button", class: "menu-item plain", onclick: () => exp("pdf") }, "Download PDF")));
    main.replaceChildren(
      el("div", { class: "narrow" },
        pageHead("History", null, dl, el("button", { class: "btn primary", onclick: () => addTransactionModal() }, icon("plus"), "Add")),
        el("div", { class: "stack", style: { gap: "10px", marginBottom: "14px" } }, kindSeg,
          el("div", { class: "row", style: { gap: "8px" } }, q, filterBtn), filters),
        el("div", { class: "card list-card" }, list, more)));
    reload();
  }

  document.addEventListener("DOMContentLoaded", () => window.Kitna.boot(render));
})();
