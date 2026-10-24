import os
import sqlite3

db_path = os.path.join("data", "table", "gold.db")

def into_sqllite(data, timestamp):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print (f"Storing data: {data} at {timestamp}")
    cursor.execute("CREATE TABLE IF NOT EXISTS bursaGold (timedate TEXT PRIMARY KEY, buy_price INTEGER, sell_price INTEGER, volume INTEGER)")

    add_bursa = ("INSERT OR REPLACE INTO bursaGold "
                "(timedate, buy_price, sell_price, volume) "
                "VALUES (?, ?, ?, ?)")
                
    bursaBuyPrice = data.get("bursaBuyPrice", 0)
    bursaSellPrice = data.get("bursaSellPrice", 0)   
    Volume = bursaBuyPrice - bursaSellPrice


    cursor.execute(add_bursa, (timestamp, bursaBuyPrice, bursaSellPrice, Volume))
    conn.commit()
    conn.close()