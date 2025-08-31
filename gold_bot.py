import requests
import time
import logging
import os
import random

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")

# الأسعار الابتدائية التجريبية
BASE_PRICES = {
    "ounce_usd": 1950.50,
    "gram_usd": 62.73,
    "gram_iqd": 915000
}

last_update_id = None

def generate_fake_prices():
    prices = {}
    prices["ounce_usd"] = round(BASE_PRICES["ounce_usd"] + random.uniform(-5, 5), 2)
    prices["gram_usd"] = round(prices["ounce_usd"] / 31.1035, 2)
    prices["gram_iqd"] = int(prices["gram_usd"] * 14580)
    return prices

def send_to_telegram(message: str, chat_id=CHAT_ID):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=payload)
    if r.status_code != 200:
        logging.error(f"❌ Telegram error: {r.text}")
    else:
        logging.info("📩 Message sent to Telegram!")

def format_price_message(prices: dict):
    message = (
        "💰 **تحديث أسعار الذهب** 💰\n\n"
        f"🔸 **الأونصة:** `{prices['ounce_usd']:.2f}` $\n"
        f"🔸 **الغرام بالدولار:** `{prices['gram_usd']:.2f}` $\n"
        f"🔸 **الغرام بالدينار العراقي:** `{prices['gram_iqd']:,}` IQD\n\n"
        "_للحصول على التحديث الفوري، استخدم الأمر /price_"
    )
    return message

def handle_updates():
    global last_update_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    if last_update_id:
        url += f"?offset={last_update_id + 1}"
    r = requests.get(url)
    updates = r.json()

    for update in updates.get("result", []):
        last_update_id = update["update_id"]
        if "message" in update:
            text = update["message"].get("text", "")
            chat_id = update["message"]["chat"]["id"]
            if text == "/price":
                prices = generate_fake_prices()
                message = format_price_message(prices)
                send_to_telegram(message, chat_id)

def main_loop():
    while True:
        # توليد أسعار جديدة
        prices = generate_fake_prices()
        message = format_price_message(prices)
        send_to_telegram(message)

        # الرد على أوامر /price
        handle_updates()

        # الانتظار ساعة كاملة قبل التحديث التالي
        time.sleep(3600)  # 3600 ثانية = ساعة واحدة

if __name__ == "__main__":
    logging.info("🚀 Gold Bot التجريبي بدأ!")
    main_loop()
