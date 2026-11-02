"""PDF exports (reportlab)."""
import io
from . import clock

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ORANGE = colors.HexColor("#e8491d")
INK = colors.HexColor("#1b1b24")
MUTED = colors.HexColor("#6b6b80")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], textColor=INK, fontSize=20, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=INK, fontSize=13, spaceBefore=12, spaceAfter=6),
        "p": ParagraphStyle("p", parent=ss["BodyText"], textColor=INK, fontSize=10, leading=14),
        "muted": ParagraphStyle("m", parent=ss["BodyText"], textColor=MUTED, fontSize=9),
    }


def _table(rows, widths, money_cols=()):
    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f7")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddde4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for c in money_cols:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _inr(v):
    return f"Rs {v:,.2f}"


def transactions_pdf(user, txs):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="Flux transactions")
    s = _styles()
    story = [Paragraph("Flux — Transactions", s["h1"]),
             Paragraph(f"{_esc(user['name'])} · generated {clock.now():%d %b %Y, %H:%M}", s["muted"]),
             Spacer(1, 8)]
    rows = [["Date", "Type", "Category", "Note", "Amount"]]
    for t in txs:
        rows.append([t["date"], t["kind"].title(), _esc(t["category"]), Paragraph(_esc(t["note"])[:80], s["p"]),
                     _inr(t["amount"])])
    if len(rows) == 1:
        rows.append(["—", "", "No transactions", "", ""])
    story.append(_table(rows, [24 * mm, 20 * mm, 36 * mm, 68 * mm, 30 * mm], money_cols=(4,)))
    doc.build(story)
    buf.seek(0)
    return buf


def monthly_pdf(user, snap):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title="Flux monthly report")
    s = _styles()
    m = snap["this_month"]
    story = [Paragraph(f"Flux monthly report — {_esc(m['month'])}", s["h1"]),
             Paragraph(f"Prepared for {_esc(user['name'])}", s["muted"]), Spacer(1, 10)]

    rate = f"{m['savings_rate']}%" if m["savings_rate"] is not None else "—"
    story.append(_table([["Income", "Expenses", "Moved to goals", "Savings rate", "Balance now"],
                         [_inr(m["income"]), _inr(m["expenses"]), _inr(m["saved"]), rate, _inr(snap["balance"])]],
                        [34 * mm] * 5))

    h = snap["health"]
    story.append(Paragraph("Money Health Score", s["h2"]))
    if h["score"] is None:
        story.append(Paragraph("Not enough data yet.", s["p"]))
    else:
        story.append(Paragraph(f"<b>{h['score']} / 100</b>", s["p"]))
        story.append(_table([["Part", "Points", "Detail"]] +
                            [[p["name"], f"{p['points']} / {p['max']}", _esc(p["detail"])] for p in h["parts"]],
                            [45 * mm, 25 * mm, 100 * mm]))
        for tip in h["tips"]:
            story.append(Paragraph("• " + _esc(tip), s["p"]))

    story.append(Paragraph("Where the money went", s["h2"]))
    cats = [["Category", "Spent", "Share"]]
    for c in m["by_category"]:
        share = c["amount"] / m["expenses"] * 100 if m["expenses"] else 0
        cats.append([_esc(c["category"]), _inr(c["amount"]), f"{share:.0f}%"])
    if len(cats) == 1:
        cats.append(["No expenses this month", "", ""])
    story.append(_table(cats, [80 * mm, 50 * mm, 40 * mm], money_cols=(1, 2)))

    if snap["budgets"]:
        story.append(Paragraph("Budgets", s["h2"]))
        story.append(_table([["Category", "Budget", "Spent", "Used"]] +
                            [[_esc(b["category"]), _inr(b["limit"]), _inr(b["spent"]), f"{b['percent']:.0f}%"]
                             for b in snap["budgets"]], [60 * mm, 40 * mm, 40 * mm, 30 * mm], money_cols=(1, 2, 3)))
    if snap["goals"]:
        story.append(Paragraph("Goals", s["h2"]))
        story.append(_table([["Goal", "Saved", "Target", "Progress"]] +
                            [[_esc(g["title"]), _inr(g["saved"]), _inr(g["target"]), f"{g['percent']:.0f}%"]
                             for g in snap["goals"]], [60 * mm, 40 * mm, 40 * mm, 30 * mm], money_cols=(1, 2, 3)))

    f = snap["forecast"]
    story.append(Paragraph("Month-end forecast", s["h2"]))
    story.append(Paragraph(f"Projected spending this month: <b>{_inr(f['projected_month_total'])}</b> "
                           f"(last month: {_inr(f['last_month_total'])}). {_esc(f['method'])}", s["p"]))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Flux is a budgeting tool, not financial advice.", s["muted"]))
    doc.build(story)
    buf.seek(0)
    return buf
