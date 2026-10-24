from html import escape

from src.common.conn_details import get_latest_stocks
from src.notify.telegram import send_message


def format_stock(row):
    arrow = "🔺" if (row.get("change") or 0) >= 0 else "🔻"
    return (
        f"{arrow} <b>{escape(str(row['symbol']))}</b> "
        f"{escape(str(row['name']))}\n"
        f"   Price: {row['price']}  "
        f"Change: {row['change']}  "
        f"Volume: {row['volume']:,}"
    )


def build_message(rows):
    if not rows:
        return "No stock data available yet."

    lines = ["📈 <b>Latest prices</b>", ""]
    lines.extend(format_stock(row) for row in rows)
    lines.append("")
    lines.append(f"<i>as of {rows[0]['scraped_at']}</i>")
    return "\n".join(lines)


def notify_latest(limit=10):
    """Read the latest rows from the database and push them to Telegram."""
    rows = get_latest_stocks(limit=limit)
    message = build_message(rows)
    return send_message(message)
