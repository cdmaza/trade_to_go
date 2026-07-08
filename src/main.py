from extract.get_gold import get_gold
from data.store_gold import into_goldtable, db_path
from notify.notifier import notify_gold, notify_new_low_buy, notify_new_high_sell
from datetime import datetime
import sqlite3

SQL_PATH = "sql/queries/max_prices.sql"

now = datetime.now()
string_date = now.strftime("%Y-%m-%d %H:%M:%S")

def get_MinMax():
    with open(SQL_PATH) as f:
        query = f.read()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(query)
    buy_date, min_buy, sell_date, max_sell = cursor.fetchone()
    conn.close()

    return min_buy, buy_date, max_sell, sell_date

def compare_gold_prices(data):
    min_buy, buy_date, max_sell, sell_date = get_MinMax()
    buy = data.get("bursaBuyPrice")
    sell = data.get("bursaSellPrice")

    if min_buy is None or max_sell is None:
        print("No historical gold data yet.")
        return

    if buy < min_buy:
        print(f"✅ New lowest buy price: {buy} (was {min_buy} at {buy_date})")
        notify_new_low_buy(buy, min_buy, buy_date, string_date)

    if sell > max_sell:
        print(f"✅ New highest sell price: {sell} (was {max_sell} at {sell_date})")
        notify_new_high_sell(sell, max_sell, sell_date, string_date)

def run_gold():
    data = get_gold()
    compare_gold_prices(data)
    into_goldtable(data, string_date)
    notify_gold(data, string_date)
    print(f"Scraped and stored {string_date} gold data.")


def run():
    run_gold()

if __name__ == "__main__":
    run()
