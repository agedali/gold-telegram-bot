import os
import requests
import datetime

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLD_API_KEY     = os.getenv("GOLD_API_KEY")  # ضع مفتاحك هنا كـ Secret

TROY_OUNCE_TO_GRAM = 31.1034768

def get_spot_xau_usd():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLD_API_KEY, "Content-Type": "application/json"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    return float(data["price"])

def get_usd_to_iqd():
    url = "https://api.exchangerate.host/latest?base=USD&symbols=IQD"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return float(r.json()["rates"]["IQD"])

def format_prices(ounce_usd, usd_to_iqd):
    gram_usd_24 = ounce_usd / TROY_OUNCE_TO_GRAM
    gram_usd_21 = gram_usd_24 * (21/24)
    gram_usd_18 = gram_usd_24 * (18/24)

    ounce_iqd = ounce_usd * usd_to_iqd
    gram_iqd_24 = gram_usd_24 * usd_to_iqd
    gram_iqd_21 = gram_usd_21 * usd_to_iqd
    gram_iqd_18 = gram_usd_18 * usd_to_iqd

    def fmt(x, nd=2):
        return f"{x:,.{nd}f}"

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"🟡 أسعار الذهب الفوري — {now}\\n"
        f"الأونصة: {fmt(ounce_usd,2)} $ — {fmt(ounce_iqd,0)} د.ع\\n"
        f"الغرام: 24K {fmt(gram_usd_24,2)} $ — {fmt(gram_iqd_24,0)} د.ع\\n"
        f"21K {fmt(gram_usd_21,2)} $ — {fmt(gram_iqd_21,0)} د.ع\\n"
        f"18K {fmt(gram_usd_18,2)} $ — {fmt(gram_iqd_18,0)} د.ع\\n"
        f"⚙️ مصدر: GoldAPI + exchangerate.host"
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
    usd_to_iqd = get_usd_to_iqd()
    msg = format_prices(ounce_usd, usd_to_iqd)
    send_to_telegram(msg)

if __name__ == "__main__":
    main()
