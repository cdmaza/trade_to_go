"""Command-line entry point (`ttg`). systemd timers call these commands."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import typer

from trade_to_go.core import storage
from trade_to_go.core.config import get_settings
from trade_to_go.core.log import setup_logging
from trade_to_go.pipelines import equities, gold

log = logging.getLogger("trade_to_go")
app = typer.Typer(no_args_is_help=True, help="trade_to_go data and alert pipeline.")

# source name -> (fetch to raw, rebuild staging)
INGESTERS: dict[str, tuple[Callable, Callable]] = {
    "bgd": (gold.ingest_bgd, gold.build_bgd_staging),
    "bnm": (gold.ingest_bnm, gold.build_bnm_staging),
    "worldbank": (gold.ingest_worldbank, gold.build_worldbank_staging),
    "fred": (gold.ingest_fred, gold.build_fred_staging),
    "lbma": (lambda: [], gold.build_lbma_staging),  # fetched by `ttg import lbma`
    "tiingo": (lambda: equities.ingest_prices("tiingo"), equities.build_prices_staging),
    "moomoo": (lambda: equities.ingest_prices("moomoo"), equities.build_prices_staging),
    "edgar": (equities.ingest_edgar, equities.build_edgar_staging),
}


def _check_source(source: str) -> None:
    if source not in INGESTERS:
        raise typer.BadParameter(f"unknown source {source!r}; choose from {', '.join(INGESTERS)}")


@app.callback()
def main(log_level: str = typer.Option("INFO", help="Logging level.")) -> None:
    setup_logging(log_level)


@app.command()
def init() -> None:
    """Create the data folders and the ops.sqlite schema."""
    settings = get_settings()
    for folder in (settings.raw_dir, settings.staging_dir, settings.curated_dir, settings.reports_dir):
        folder.mkdir(parents=True, exist_ok=True)
    storage.ops().close()
    typer.echo(f"Initialised {settings.data_dir}")


@app.command()
def ingest(source: str = typer.Argument(..., help=f"One of: {', '.join(INGESTERS)}")) -> None:
    """Fetch a source into raw/ and rebuild its staging dataset."""
    _check_source(source)
    fetch, stage = INGESTERS[source]
    with storage.track_run(f"ingest:{source}"):
        landed = fetch()
        log.info("raw: %d file(s)", len(landed))
        log.info("staging: %s", stage())


@app.command()
def stage(source: str = typer.Argument(..., help=f"One of: {', '.join(INGESTERS)}")) -> None:
    """Rebuild a staging dataset from raw/ without fetching."""
    _check_source(source)
    with storage.track_run(f"stage:{source}"):
        log.info("staging: %s", INGESTERS[source][1]())


@app.command("import")
def import_file(source: str = typer.Argument(..., help="lbma"),
                file: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Import a manually downloaded file (LBMA portal) into raw/ and rebuild staging."""
    if source != "lbma":
        raise typer.BadParameter("only 'lbma' is imported from a file")
    with storage.track_run("import:lbma"):
        gold.import_lbma(file)
        log.info("staging: %s", gold.build_lbma_staging())


@app.command()
def build(dataset: str = typer.Argument("gold", help="gold")) -> None:
    """Build curated datasets."""
    if dataset != "gold":
        raise typer.BadParameter("only 'gold' so far")
    with storage.track_run("build:gold"):
        log.info("curated: %s", gold.build_gold_curated())


@app.command()
def reconcile() -> None:
    """Reconcile the MYR gold series against Kijang Emas, BGD and the World Bank; write a report."""
    from trade_to_go.reconcile.gold_myr import run

    with storage.track_run("reconcile:gold"):
        result = run()
    typer.echo(f"Report: {result['report']}")
    for check in result["checks"]:
        typer.echo(f"  {check['name']:<28} {check['status']}")


@app.command()
def backtest(study: str = typer.Argument("gold", help="gold"),
             provisional: bool = typer.Option(False, help="Use World Bank monthly averages (biased; no decision).")) -> None:
    """Run a study and write its report to reports/."""
    if study != "gold":
        raise typer.BadParameter("only 'gold' so far")
    from trade_to_go.backtest.gold_study import run

    with storage.track_run(f"backtest:{study}"):
        result = run(provisional=provisional)
    typer.echo(f"Report: {result['report']}")
    typer.echo(f"Decision: {result['decision']['answer']} - {result['decision']['why']}")


@app.command()
def screen(market: str = typer.Argument("us", help="us")) -> None:
    """US long term: ETF 10-month trend states and the quality/value/momentum picks."""
    if market != "us":
        raise typer.BadParameter("only 'us' so far")
    with storage.track_run("screen:us"):
        typer.echo(f"Report: {equities.us_report()}")


@app.command()
def export() -> None:
    """Write all staging/curated gold datasets and the latest reconciliation to Excel."""
    from trade_to_go.pipelines.export import export_excel

    with storage.track_run("export:excel"):
        typer.echo(f"Excel: {export_excel()}")


@app.command()
def call(refresh: bool = typer.Option(False, "--refresh", help="Fetch fresh prices first (BNM; Tiingo if a key is set)."),
         notify: bool = typer.Option(False, "--notify", help="Send a Telegram digest when a call changed."),
         html: bool = typer.Option(True, help="Write reports/dashboard.html."),
         markdown: bool = typer.Option(False, "--markdown", help="Print Markdown instead of the terminal view.")) -> None:
    """Today's buy / hold / sell call for gold, your watchlist and a few potential stocks."""
    from trade_to_go.calls import render, service
    from trade_to_go.core.telegram import send_message

    with storage.track_run("call"):
        notes = service.refresh() if refresh else []
        report = service.build_report()
        report.notes[:0] = notes
        changes = service.record_changes(report)
        service.save(report)
        folder = get_settings().reports_dir
        md = render.render_markdown(report)
        (folder / "call_latest.md").write_text(md, encoding="utf-8")
        if html:
            (folder / "dashboard.html").write_text(render.render_html(report), encoding="utf-8")
        if markdown:
            typer.echo(md)
        else:
            render.render_terminal(report)
            if html:
                typer.echo(f"\nDashboard: {folder / 'dashboard.html'}")
        if notify:
            if changes:
                send_message(render.render_telegram(report, changes))
                typer.echo(f"Telegram: sent ({len(changes)} change(s))")
            else:
                typer.echo("Telegram: nothing changed, nothing sent")


watch_app = typer.Typer(no_args_is_help=True, help="Your own stock list (always shown in `ttg call`).")
app.add_typer(watch_app, name="watch")


@watch_app.command("add")
def watch_add(symbols: list[str] = typer.Argument(..., help="Tickers, e.g. AAPL MSFT")) -> None:
    """Add stocks to your watchlist."""
    from trade_to_go.calls import watchlist

    try:
        typer.echo("Watchlist: " + ", ".join(watchlist.add(symbols)))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo("Run `ttg call --refresh` to fetch their prices (needs TIINGO_API_KEY).")


@watch_app.command("remove")
def watch_remove(symbols: list[str] = typer.Argument(...)) -> None:
    """Remove stocks from your watchlist."""
    from trade_to_go.calls import watchlist

    typer.echo("Watchlist: " + (", ".join(watchlist.remove(symbols)) or "(empty)"))


@watch_app.command("list")
def watch_list() -> None:
    """Show your watchlist."""
    from trade_to_go.calls import watchlist

    typer.echo(", ".join(watchlist.load()) or "(empty)")


alerts_app = typer.Typer(no_args_is_help=True, help="Evaluate, send and score alerts.")
app.add_typer(alerts_app, name="alerts")


@alerts_app.command("run")
def alerts_run(dry_run: bool = typer.Option(False, help="Evaluate and log, but do not send to Telegram.")) -> None:
    """Evaluate every enabled signal; alert on state changes only."""
    from trade_to_go.alerts.service import process
    from trade_to_go.core.config import load_yaml
    from trade_to_go.core.telegram import send_message
    from trade_to_go.signals.live import evaluate

    specs = {k: v for k, v in load_yaml("alerts.yaml").get("signals", {}).items() if v.get("enabled")}
    if not specs:
        typer.echo("No enabled signals (the backtest has not earned one; the answer is DCA).")
        return
    with storage.track_run("alerts:run"):
        for name, spec in specs.items():
            signal = evaluate(name, spec)
            alert_id = process(signal, send=None if dry_run else send_message)
            typer.echo(f"{name}: {signal.state} @ {signal.price:,.2f}" + (f" -> alert #{alert_id}" if alert_id else ""))


@alerts_app.command("score")
def alerts_score() -> None:
    """Fill 5/20/60-day forward scores for logged alerts."""
    from trade_to_go.alerts.scorer import benchmark_from_config, score_pending
    from trade_to_go.pipelines.prices import price_series

    with storage.track_run("alerts:score"):
        typer.echo(f"Scored {score_pending(price_series, benchmark_from_config)} horizon(s)")


@alerts_app.command("report")
def alerts_report() -> None:
    """Forward-scored alert log vs benchmark (success criterion 3)."""
    from trade_to_go.alerts.scorer import summary

    typer.echo(summary().to_string(index=False))


@app.command()
def status(limit: int = 10) -> None:
    """Show recent runs and dataset row counts."""
    con = storage.ops()
    for row in con.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT ?", (limit,)):
        typer.echo(f"{row['started_at']}  {row['status']:<7}  {row['job']}  {row['detail'] or ''}")
    con.close()

    wh = storage.warehouse()
    for (name,) in wh.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1").fetchall():
        count = wh.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        typer.echo(f"{name}: {count} rows")
    wh.close()


if __name__ == "__main__":
    app()
