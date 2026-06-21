import websocket
import json

result = {}

def on_message(ws, message):
    data = json.loads(message)
    result.update(data)
    ws.close()

def on_error(ws, error):
    print("Error:", error)

headers = {
    "Origin": "https://bgd.bursamalaysia.com",
    "Host": "bgd-adam.bursamalaysia.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

app = websocket.WebSocketApp(
    "wss://bgd-adam.bursamalaysia.com/bgd/pricestream",
    on_message=on_message,
    on_error=on_error,
    header=headers,
)
app.run_forever()

def get_gold():
    return {
        "bursaBuyPrice": result.get("bursaBuyPrice", 0),
        "bursaSellPrice": result.get("bursaSellPrice", 0)
    }
