import os
import requests
import datetime

# من Secrets في GitHub
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDPRICEZ_KEY   = os.getenv("GOLDPRICEZ_API_KEY")
ALANCHAND_KEY    = os.getenv("ALANCHAND_API_KEY")

def get_usd_to_iqd():
    url = "https://api.alanchand.com?type=currency&symbols=usd"
    headers = {"Authorization": f"Bearer {ALANCHAND_KEY}"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    return float(data["data"]["usd"]["iqd"])

def get_gold_prices_usd():
    url = "https://goldpricez.com/api/rates/currency/usd/measure/all"
    headers = {"X-API-KEY": GOLDPRICEZ_KEY}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

def format_message(usd_to_iqd, gold_data):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    ounce_usd = gold_data["gold_per_ounce"]
    g24_usd   = gold_data["gold_per_gram_24k"]
    g21_usd   = gold_data["gold_per_gram_21k"]
    g18_usd   = gold_data["gold_per_gram_18k"]

    ounce_iqd = ounce_usd * usd_to_iqd
    g24_iqd   = g24_usd * usd_to_iqd
    g21_iqd   = g21_usd * usd_to_iqd
    g18_iqd   = g18_usd * usd_to_iqd

    def fmt(x, nd=2):
        return f"{x:,.{nd}f}"

    text = (
        f"📊 التحديث: {now}\n\n"
        f"💵 سعر الصرف\n"
        f"1 دولار = {fmt(usd_to_iqd,0)} د.ع\n\n"
        f"🏅 أسعار الذهب\n"
        f"🟡 الأونصة: {fmt(ounce_usd,2)} $ — {fmt(ounce_iqd,0)} د.ع\n"
        f"🥇 24K: {fmt(g24_usd,2)} $ — {fmt(g24_iqd,0)} د.ع\n"
        f"🥈 21K: {fmt(g21_usd,2)} $ — {fmt(g21_iqd,0)} د.ع\n"
        f"🥉 18K: {fmt(g18_usd,2)} $ — {fmt(g18_iqd,0)} د.ع"
    )
    return text

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def main():
    usd_to_iqd = get_usd_to_iqd()
    gold_data  = get_gold_prices_usd()
    msg = format_message(usd_to_iqd, gold_data)
    send_to_telegram(msg)

if __name__ == "__main__":
    main()
