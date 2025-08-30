import os
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDPRICEZ_API_KEY = os.getenv("GOLDPRICEZ_API_KEY")

def get_spot_xau_usd():
    url = f"https://goldpricez.com/api/rates/currency/usd/measure/all?api_key={GOLDPRICEZ_API_KEY}"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()
    # السعر للأونصة بالدولار
    return float(data["ounce"])

def send_to_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=payload)

def main():
    ounce_usd = get_spot_xau_usd()
    message = (
        "💰 أسعار الذهب اليوم\n\n"
        f"🔸 أونصة الذهب = {ounce_usd:,.2f} دولار\n"
    )
    send_to_telegram(message)

if __name__ == "__main__":
    main()
