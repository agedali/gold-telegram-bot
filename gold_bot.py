import os
import requests
import datetime

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDPRICEZ_API_KEY = os.getenv("GOLDPRICEZ_API_KEY")

TROY_OUNCE_TO_GRAM = 31.1034768

def get_spot_xau_usd():
    url = f"https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDPRICEZ_API_KEY, "Content-Type": "application/json"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    return float(data["price"])

def format_prices(ounce_usd):
    gram_usd_24 = ounce_usd / TROY_OUNCE_TO_GRAM
    gram_usd_21 = gram_usd_24 * (21/24)
    gram_usd_18 = gram_usd_24 * (18/24)

    def fmt(x, nd=2):
        return f"{x:,.{nd}f}"

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"🟡 أسعار الذهب بالدولار — {now}\n"
        f"الأونصة: {fmt(ounce_usd,2)} $\n"
        f"الغرام:\n"
        f"   24K — {fmt(gram_usd_24,2)} $\n"
        f"   21K — {fmt(gram_usd_21,2)} $\n"
        f"   18K — {fmt(gram_usd_18,2)} $\n"
    )
    return text

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def main():
    ounce_usd = get_spot_xau_usd()
    msg = format_prices(ounce_usd)
    send_to_telegram(msg)

if __name__ == "__main__":
    main()
