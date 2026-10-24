"""Renderers for a Report: terminal (rich), Markdown, Telegram HTML and a standalone HTML dashboard."""

from __future__ import annotations

from html import escape

from rich.console import Console
from rich.table import Table
from rich.text import Text

from trade_to_go.calls.models import BUY, HOLD, NA, SELL, Call
from trade_to_go.calls.service import Report

COLORS = {BUY: "green", HOLD: "yellow", SELL: "red", NA: "dim"}
EMOJI = {BUY: "🟢", HOLD: "🟡", SELL: "🔴", NA: "⚪"}
DISCLAIMER = ("Trend and momentum readings from price data only. Not financial advice, and not a validated "
              "edge: the gold backtest has not named a rule that beats plain monthly DCA.")


def pct(x: float | None, signed: bool = True) -> str:
    return "-" if x is None else f"{x:+.1%}" if signed else f"{x:.0%}"


def levels_line(g: Call) -> str:
    """Price levels that would weaken a gold call, as one sentence ('' when unknown)."""
    parts = [f"{v:,.0f} ({name})" for name, v in (("10-month average", g.levels.get("sma10_flip")),
                                                  ("price 12 months ago", g.levels.get("tsmom12_flip"))) if v]
    return f"Checks flip around: {' and '.join(parts)} {g.currency}." if parts else ""


def _vs_flip(c: Call) -> str:
    flip = c.levels.get("sma10_flip")
    return "-" if not flip or not c.price else pct(c.price / flip - 1)


def _price(c: Call) -> str:
    return "-" if c.price is None else f"{c.price:,.2f}" if c.kind == "stock" else f"{c.price:,.0f}"


def _rsi(c: Call) -> str:
    v = c.metrics.get("rsi14")
    return "-" if v is None else f"{v:.0f}"


def _stock_note(c: Call) -> str:
    """What to watch: tags and cautions first, else the price level that would change the call."""
    if c.tags or c.cautions:
        return "; ".join([*c.tags, *c.cautions])
    flip = c.levels.get("sma10_flip")
    if c.label == BUY and flip:
        return f"Uptrend; trend breaks below {flip:,.2f}"
    if c.label == SELL and flip:
        return f"Downtrend; turns up above {flip:,.2f}"
    return c.summary


# ---------------------------------------------------------------- terminal

def _stock_table(title: str, calls: list[Call]) -> Table:
    t = Table(title=title, title_justify="left", header_style="bold", box=None, pad_edge=False)
    for col, just in (("Stock", "left"), ("Call", "left"), ("Price", "right"), ("vs trend line", "right"),
                      ("3m", "right"), ("12m", "right"), ("RSI", "right"), ("Note", "left")):
        t.add_column(col, justify=just, overflow="fold")
    for c in calls:
        t.add_row(c.symbol, Text(c.label, style=f"bold {COLORS[c.label]}"), _price(c), _vs_flip(c),
                  pct(c.metrics.get("ret_3m")), pct(c.metrics.get("ret_12m")), _rsi(c), _stock_note(c))
    return t


def render_terminal(r: Report, console: Console | None = None) -> None:
    console = console or Console()
    console.print(f"[bold]TRADE TO GO[/bold]  call for {r.today}\n")

    console.print("[bold]GOLD (MYR)[/bold]")
    if r.gold is None:
        console.print(f"  {r.gold_error}\n")
    else:
        g = r.gold
        console.print(Text.assemble("  ", (f" {g.label} ", f"bold reverse {COLORS[g.label]}"),
                                    f"  {g.price:,.0f} {g.currency}  (price as of {g.as_of}; {', '.join(g.tags)})"))
        console.print(f"  {g.summary}")
        for line in g.reasons:
            console.print(f"    - {line}")
        line = levels_line(g)
        if line:
            console.print(f"    - {line}")
        for line in g.cautions:
            console.print(f"    [yellow]![/yellow] {line}")
        console.print()

    console.print("[bold]YOUR STOCKS[/bold]")
    if r.watchlist:
        console.print(_stock_table("", r.watchlist))
    else:
        console.print("  (none with prices yet)")
    if r.missing:
        console.print(f"  [dim]No price data for: {', '.join(r.missing)}[/dim]")
    console.print()

    console.print(f"[bold]POTENTIAL STOCKS[/bold]  [dim](top {len(r.potential)} of {r.pool_buys} buy-rated, "
                  f"{r.pool_size} scanned)[/dim]")
    if r.potential:
        console.print(_stock_table("", r.potential))
    else:
        console.print("  (none right now)" if r.pool_size else "  (no candidate prices yet)")
    console.print()
    for n in r.notes:
        console.print(f"[yellow]Note:[/yellow] {n}")
    console.print(f"[dim]{DISCLAIMER}[/dim]")


# ---------------------------------------------------------------- markdown

def render_markdown(r: Report) -> str:
    out = [f"# Trade To Go - call for {r.today}", ""]
    out.append("## Gold (MYR)")
    if r.gold is None:
        out += [r.gold_error or "No gold data.", ""]
    else:
        g = r.gold
        out += [f"**{g.label}** at {g.price:,.0f} {g.currency} (price as of {g.as_of}; {', '.join(g.tags)})", "",
                g.summary, ""]
        out += [f"- {x}" for x in g.reasons]
        out += [f"- Watch out: {x}" for x in g.cautions]
        out.append("")

    def table(calls: list[Call]) -> list[str]:
        rows = ["| Stock | Call | Price | vs trend line | 3m | 12m | RSI | Note |", "|---|---|---:|---:|---:|---:|---:|---|"]
        rows += [f"| {c.symbol} | **{c.label}** | {_price(c)} | {_vs_flip(c)} | {pct(c.metrics.get('ret_3m'))} | "
                 f"{pct(c.metrics.get('ret_12m'))} | {_rsi(c)} | {_stock_note(c)} |" for c in calls]
        return rows

    out += ["## Your stocks", *(table(r.watchlist) if r.watchlist else ["(none with prices yet)"]), ""]
    out += [f"## Potential stocks (top {len(r.potential)} of {r.pool_buys} buy-rated, {r.pool_size} scanned)",
            *(table(r.potential) if r.potential else ["(none right now)"]), ""]
    out += [f"> Note: {n}" for n in r.notes]
    out += ["", f"_{DISCLAIMER}_", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- telegram

def render_telegram(r: Report, changes: list[tuple[Call, str | None]] | None = None) -> str:
    lines = [f"<b>Trade To Go</b> · {escape(r.today)}"]
    if changes:
        lines.append("")
        lines.append("<b>What changed</b>")
        for c, prev in changes:
            lines.append(f"{EMOJI[c.label]} <b>{escape(c.symbol)}</b>: {escape(prev or 'new')} → <b>{escape(c.label)}</b>"
                         f" @ {_price(c)}")
    if r.gold:
        g = r.gold
        lines += ["", f"{EMOJI[g.label]} <b>Gold {escape(g.label)}</b> · {g.price:,.0f} {escape(g.currency)}",
                  escape(g.summary)]
    for title, calls in (("Your stocks", r.watchlist), ("Potential", r.potential)):
        if calls:
            lines += ["", f"<b>{title}</b>"]
            lines += [f"{EMOJI[c.label]} {escape(c.symbol)} {escape(c.label)} · {_price(c)} · 12m {pct(c.metrics.get('ret_12m'))}"
                      for c in calls]
    lines += ["", f"<i>{escape(DISCLAIMER)}</i>"]
    return "\n".join(lines)[:4000]


# ---------------------------------------------------------------- html dashboard

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--muted:#5d6675;--line:#e3e6ec;--buy:#12805c;--buy-bg:#e2f4ec;
--hold:#9a6700;--hold-bg:#fbf0d4;--sell:#b42318;--sell-bg:#fde7e4;--na:#5d6675;--na-bg:#eceef2}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--card:#171b22;--ink:#e8ebf0;--muted:#9aa3b2;--line:#262c36;
--buy:#4cc38a;--buy-bg:#12281f;--hold:#e3b341;--hold-bg:#2b2410;--sell:#ff7b72;--sell-bg:#33161a;--na:#9aa3b2;--na-bg:#20252e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 2px}h2{font-size:15px;
text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:28px 0 10px}.sub{color:var(--muted);margin:0 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:700;font-size:13px}
.BUY{color:var(--buy);background:var(--buy-bg)}.HOLD{color:var(--hold);background:var(--hold-bg)}
.SELL{color:var(--sell);background:var(--sell-bg)}.NA{color:var(--na);background:var(--na-bg)}
.big{font-size:30px;font-weight:700;margin:6px 0}.row{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
ul{margin:8px 0;padding-left:20px}li{margin:3px 0}.warn{color:var(--hold)}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:640px}
th,td{text-align:right;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2),th:last-child,td:last-child{text-align:left}
td:last-child{white-space:normal;color:var(--muted);min-width:200px}th{color:var(--muted);font-weight:600;font-size:13px}
.note{color:var(--muted);font-size:13px;margin-top:28px}
"""


def _html_table(calls: list[Call]) -> str:
    if not calls:
        return '<div class="card sub">None right now.</div>'
    rows = "".join(
        f"<tr><td><b>{escape(c.symbol)}</b></td><td><span class='badge {c.label.replace('/', '')}'>{escape(c.label)}</span></td>"
        f"<td>{_price(c)}</td><td>{_vs_flip(c)}</td><td>{pct(c.metrics.get('ret_3m'))}</td>"
        f"<td>{pct(c.metrics.get('ret_12m'))}</td><td>{_rsi(c)}</td><td>{escape(_stock_note(c))}</td></tr>"
        for c in calls)
    return ("<div class='card scroll'><table><thead><tr><th>Stock</th><th>Call</th><th>Price</th><th>vs trend line</th>"
            f"<th>3m</th><th>12m</th><th>RSI</th><th>Note</th></tr></thead><tbody>{rows}</tbody></table></div>")


def render_html(r: Report) -> str:
    if r.gold:
        g = r.gold
        lis = "".join(f"<li>{escape(x)}</li>" for x in g.reasons)
        warn = "".join(f"<li class='warn'>{escape(x)}</li>" for x in g.cautions)
        levels = f"<p class='sub'>{escape(levels_line(g))}</p>" if levels_line(g) else ""
        gold = (f"<div class='card'><div class='row'><span class='badge {g.label.replace('/', '')}'>{escape(g.label)}</span>"
                f"<span class='sub'>price as of {escape(g.as_of)} · {escape(', '.join(g.tags))}</span></div>"
                f"<div class='big'>{g.price:,.0f} <span class='sub'>{escape(g.currency)}</span></div>"
                f"<p><b>{escape(g.summary)}</b></p>{levels}<ul>{lis}{warn}</ul></div>")
    else:
        gold = f"<div class='card sub'>{escape(r.gold_error or 'No gold data.')}</div>"
    notes = "".join(f"<p class='note'>Note: {escape(n)}</p>" for n in r.notes)
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Trade To Go call</title><style>{CSS}</style></head><body><main>"
            f"<h1>Trade To Go</h1><p class='sub'>Call for {escape(r.today)} · generated {escape(r.generated_at)}</p>"
            f"<h2>Gold (MYR)</h2>{gold}<h2>Your stocks</h2>{_html_table(r.watchlist)}"
            f"<h2>Potential stocks <span class='sub'>top {len(r.potential)} of {r.pool_buys} buy-rated, "
            f"{r.pool_size} scanned</span></h2>{_html_table(r.potential)}{notes}"
            f"<p class='note'>{escape(DISCLAIMER)}</p></main></body></html>")
