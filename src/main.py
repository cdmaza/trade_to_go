from extract.get_gold import get_gold
from data.store_gold import into_sqllite
from datetime import datetime
import json
import os

FILE_PATH = "data/temp/goldMinMax.json"

def run():
    data = get_gold()
    now = datetime.now().isoformat(timespec="seconds")
    into_sqllite(data, now)
    print(f"Scraped and stored {now} gold data.")
    get_MinMax(data, now)


def get_MinMax(data, timedate):
    buy = data.get("bursaBuyPrice", 0)
    sell = data.get("bursaSellPrice", 0)
    low, high = min(buy, sell), max(buy, sell)

    record = {
        "min": {"price": low, "timedate": timedate},
        "max": {"price": high, "timedate": timedate},
    }

    if os.path.exists(FILE_PATH):
        with open(FILE_PATH) as f:
            current = json.load(f)

        print(current)
        if low >= current["min"]:
            record["min"] = current["min"]
        if high <= current["max"]:
            record["max"] = current["max"]
        if record == current:
            return

    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    with open(FILE_PATH, "w") as f:
        json.dump(record, f, indent=4)


if __name__ == "__main__":
    run()
