from extract.get_gold import get_gold
from data.store_gold import into_sqllite
from datetime import datetime, date

now = datetime.now()

def run():
    run_gold()


def run_gold():
    data = get_gold()
    into_sqllite(data, now)
    print(f"Scraped and stored {now} gold data.")

if __name__ == "__main__":
    run()
