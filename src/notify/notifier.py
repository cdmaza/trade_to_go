from html import escape

from common.conn_details import get_latest_stocks
from notify.telegram import send_message

#used for visual stock trend
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
        return "Message returned failed."

    lines = ["📈 <b>Latest prices</b>", ""]
    lines.extend(format_stock(row) for row in rows)
    lines.append("")
    lines.append(f"<i>as of {rows[0]['scraped_at']}</i>")
    return "\n".join(lines)


def notify_latest(limit=10):
    rows = get_latest_stocks(limit=limit)
    message = build_message(rows)
    return send_message(message)


def notify_gold(data, timedate):
    buy = data.get("bursaBuyPrice", 0)
    sell = data.get("bursaSellPrice", 0)
    message = (
        f"<b>Bursa Gold Update</b>\n"
        f"Buy:  {buy}\n"
        f"Sell: {sell}\n"
        f"<i>{timedate}</i>"
    )
    return send_message(message)


def notify_new_low_buy(buy, old_min, old_date, timedate):
    message = (
        "🟢 <b>New LOWEST buy price!</b>\n"
        f"Buy now: <b>{buy}</b>\n"
        f"Previous low: {old_min} <i>({old_date})</i>\n"
        f"<i>{timedate}</i>"
    )
    return send_message(message)


def notify_new_high_sell(sell, old_max, old_date, timedate):
    message = (
        "🔴 <b>New HIGHEST sell price!</b>\n"
        f"Sell now: <b>{sell}</b>\n"
        f"Previous high: {old_max} <i>({old_date})</i>\n"
        f"<i>{timedate}</i>"
    )
    return send_message(message)
