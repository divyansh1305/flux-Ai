/* Invest goal savings in broad, low-cost ETFs, via the user's own Zerodha account (Kite Publisher). */
(function () {
  const { el, icon, api, ok, err, modal, inr, inr0, pageHead, onRefresh } = window.Flux;
  let kiteLoading = null;

  function loadKite() {
    if (window.KiteConnect) return Promise.resolve();
    if (kiteLoading) return kiteLoading;
    kiteLoading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://kite.trade/publisher.js?v=3";
      s.onload = resolve;
      s.onerror = () => reject(new Error("Couldn't load Zerodha's order window. Check your connection."));
      document.head.appendChild(s);
    });
    return kiteLoading;
  }

  async function placeWithKite(apiKey, order) {
    await loadKite();
    return new Promise((resolve) => {
      window.KiteConnect.ready(() => {
        const kite = new window.KiteConnect(apiKey);
        kite.add(order);
        kite.finished((status) => resolve(status === "success" ? "success" : "cancelled"));
        kite.connect();
      });
    });
  }

  async function render(main) {
    const box = el("div", { class: "stack" });
    main.replaceChildren(pageHead("Invest", "Put goal savings to work in diversified funds, in your own demat account."), box);

    async function load() {
      const [opts, goals, holdings] = await Promise.all([api("/api/invest/options"), api("/api/goals"), api("/api/invest/holdings")]);
      const practice = opts.mode === "practice";
      const banner = practice
        ? el("div", { class: "notice caution" }, el("div", null, el("b", null, "Practice mode. "),
          "Orders are virtual so you can learn safely. To invest for real, the app owner adds a Zerodha Kite API key; orders then open in Zerodha's own window and go to your demat account."))
        : el("div", { class: "notice info" }, el("div", null, el("b", null, "Real investing via Zerodha. "),
          "You'll log in and confirm in Zerodha's own window. Shares go to your demat account; Flux never holds your money."));

      const total = holdings.value != null ? holdings.value : holdings.cost;
      const pnl = holdings.value != null ? holdings.value - holdings.cost : null;
      const summary = el("section", { class: "hero", style: { paddingTop: 0 } },
        el("div", null, el("div", { class: "eyebrow" }, "Invested from goals"),
          el("div", { class: "big", style: { marginTop: "12px", fontSize: "56px" } }, inr0(total)),
          el("div", { class: "sub" }, pnl == null ? `Cost ${inr0(holdings.cost)}` :
            el("span", { class: pnl >= 0 ? "green" : "red" }, `${pnl >= 0 ? "+" : ""}${inr0(pnl)} (${holdings.cost ? ((pnl / holdings.cost) * 100).toFixed(1) : "0"}%) overall`))));

      const cash = goals.filter((g) => g.cash > 0);
      const cards = opts.instruments.map((ins) => el("div", { class: "card" },
        el("div", { class: "row between" }, el("h3", null, ins.name), el("span", { class: "badge" }, ins.risk + " risk")),
        el("div", { class: "small muted", style: { margin: "8px 0 14px", minHeight: "38px" } }, ins.what),
        el("div", { class: "row between" },
          el("div", null, el("div", { class: "tiny faint" }, ins.symbol + " · NSE"), el("div", { style: { fontWeight: 800, fontSize: "20px" } }, ins.price ? inr(ins.price) : "Price unavailable")),
          el("button", { class: "btn sm primary", disabled: cash.length ? null : true, onclick: () => buy(ins, cash, opts) }, "Invest")),
        el("div", { class: "tiny faint", style: { marginTop: "10px" } }, "Suggested horizon: " + ins.horizon)));

      const rows = holdings.items.map((h) => el("tr", null,
        el("td", null, el("b", null, h.symbol), " ", h.mode === "practice" ? el("span", { class: "badge practice" }, "practice") : el("span", { class: "badge invest" }, "Zerodha"),
          el("div", { class: "tiny faint" }, h.goal ? "From " + h.goal : "", " · ", h.date)),
        el("td", { class: "right num" }, String(h.quantity)),
        el("td", { class: "right num" }, inr(h.avg_price)),
        el("td", { class: "right num" }, h.value != null ? inr(h.value) : "—"),
        el("td", { class: "right num " + (h.pnl == null ? "" : h.pnl >= 0 ? "green" : "red") }, h.pnl == null ? "—" : (h.pnl >= 0 ? "+" : "") + inr(h.pnl)),
        el("td", { class: "right" }, el("button", { class: "btn sm ghost", onclick: () => sell(h) }, h.mode === "practice" ? "Sell" : "Mark sold"))));
      const table = holdings.items.length ? el("div", { class: "table-wrap" }, el("table", { class: "table" },
        el("thead", null, el("tr", null, el("th", null, "Fund"), el("th", { class: "right" }, "Units"), el("th", { class: "right" }, "Avg price"),
          el("th", { class: "right" }, "Value"), el("th", { class: "right" }, "P&L"), el("th"))), el("tbody", null, rows)))
        : el("div", { class: "empty" }, el("b", null, "No investments yet"), cash.length ? "Pick a fund above to invest some of your goal savings." : "Save into a goal first, then invest from it here.");

      box.replaceChildren(banner, summary,
        el("div", { class: "grid g-2" }, cards),
        el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", null, "Your holdings")), table),
        el("p", { class: "tiny faint" }, opts.disclaimer + " Prices are delayed and for estimation; the final price is what your broker executes."));
    }

    async function buy(ins, goals, opts) {
      const goalSel = el("select", { class: "input" }, goals.map((g) => el("option", { value: g.id }, `${g.title} · ${inr0(g.cash)} available`)));
      const amount = el("input", { class: "input big num", type: "number", min: "1", step: "1", required: true, placeholder: "1000" });
      const price = ins.price ? null : el("input", { class: "input num", type: "number", min: "0.01", step: "0.01", required: true, placeholder: "Current price from your broker app" });
      const est = el("div", { class: "small muted" });
      const upd = () => {
        const p = ins.price || Number(price && price.value);
        const q = p ? Math.floor(Number(amount.value) / p) : 0;
        est.textContent = p && q ? `≈ ${q} unit(s) for ${inr(q * p)}` : p ? `One unit costs about ${inr(p)}.` : "";
      };
      amount.oninput = upd; if (price) price.oninput = upd;
      const v = await modal(`Invest in ${ins.name}`, el("div", { class: "form" },
        el("label", { class: "field" }, "From goal", goalSel), el("label", { class: "field" }, "Amount (₹)", amount),
        price ? el("label", { class: "field" }, "Price per unit (₹)", price) : null, est,
        el("p", { class: "tiny faint" }, opts.mode === "kite" ? "Next, Zerodha's window opens. Log in and confirm the order there." : "Practice order: no real money is invested.")),
        [{ label: "Cancel", value: null, cls: "ghost" }, { label: "Continue", submit: true, cls: "primary",
          value: () => ({ goal_id: Number(goalSel.value), symbol: ins.symbol, amount: amount.value, price: price ? price.value : undefined }) }]);
      if (!v) return;
      try {
        const prep = await api("/api/invest/prepare", { method: "POST", body: v });
        let status = "success";
        if (prep.mode === "kite") status = await placeWithKite(opts.kite_api_key, prep.kite_order);
        else {
          const yes = await modal("Confirm practice order", el("p", { class: "muted" }, `Buy ${prep.quantity} unit(s) of ${prep.symbol} at about ${inr(prep.price)} (${inr(prep.estimated_cost)}) from “${prep.goal}”.`),
            [{ label: "Cancel", value: false, cls: "ghost" }, { label: "Place practice order", value: true, cls: "primary" }]);
          status = yes ? "success" : "cancelled";
        }
        await api(`/api/invest/${prep.investment_id}/complete`, { method: "POST", body: { status } });
        if (status === "success") ok(`Bought ${prep.quantity} ${prep.symbol}.`); else ok("Order cancelled.");
        window.Flux.refresh();
      } catch (e) { err(e); }
    }

    async function sell(h) {
      const price = h.value == null || h.mode === "kite" ? el("input", { class: "input num", type: "number", min: "0.01", step: "0.01", required: true, placeholder: "Price per unit you sold at" }) : null;
      const v = await modal(h.mode === "practice" ? `Sell ${h.symbol}` : `Mark ${h.symbol} as sold`, el("div", { class: "form" },
        el("p", { class: "muted small" }, h.mode === "practice" ? `Sell ${h.quantity} unit(s) at today's price. Money goes back to “${h.goal || "your balance"}”.`
          : "Sell in your Zerodha app first, then enter the price here so Flux stays in sync."),
        price ? el("label", { class: "field" }, "Sell price (₹)", price) : null),
        [{ label: "Cancel", value: null, cls: "ghost" }, { label: "Confirm", submit: true, cls: "primary", value: () => ({ price: price ? price.value : undefined }) }]);
      if (!v) return;
      try {
        const r = await api(`/api/invest/${h.id}/sell`, { method: "POST", body: v });
        ok(`Sold for ${inr(r.proceeds)} (${r.profit >= 0 ? "+" : ""}${inr(r.profit)}).`);
        window.Flux.refresh();
      } catch (e) { err(e); }
    }

    onRefresh(load);
    await load();
  }

  document.addEventListener("DOMContentLoaded", () => window.Flux.boot(render));
})();
