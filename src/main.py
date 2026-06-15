from src.common.conn_details import init_db, insert_stocks
from src.extract.get_gold import get_gold
from src.notify.notifier import notify_latest


def run():
    init_db()

    data = get_gold()
    inserted = insert_stocks(data)
    print(f"Scraped and stored {inserted} rows.")

    notify_latest(limit=max(inserted, 1))
    print("Telegram notification sent.")


if __name__ == "__main__":
    run()
