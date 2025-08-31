import requests
import time
import logging
import os

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح من البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")

# بيانات تجريبية للذهب
TEST_PRICES = {
    "ounce_usd": 1950.50,
    "gram_usd": 62.73,
    "gram_iqd": 915000  # تقريبا حسب سعر الصرف
}

last_update_id = None  # لتجنب تكرار معالجة الرسائل

def send_to_telegram(message: str, chat_id=CHAT_ID):
    """ترسل رسالة إلى تيليغرام"""
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
    """ترجع رسالة احترافية لسعر الذهب"""
    message = (
        "💰 **سعر الذهب التجريبي اليوم** 💰\n\n"
        f"🔸 **الأونصة:** `{prices['ounce_usd']:.2f}` $ \n"
        f"🔸 **الغرام بالدولار:** `{prices['gram_usd']:.2f}` $ \n"
        f"🔸 **الغرام بالدينار العراقي:** `{prices['gram_iqd']:,}` IQD\n\n"
        "_للحصول على التحديث الفوري، استخدم الأمر /price_"
    )
    return message

def handle_updates():
    """يفحص الرسائل الجديدة ويستجيب لأمر /price"""
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
                message = format_price_message(TEST_PRICES)
                send_to_telegram(message, chat_id)

def main_loop():
    """تشغيل تلقائي + الرد على /price"""
    while True:
        # إرسال السعر التجريبي تلقائيًا
        message = format_price_message(TEST_PRICES)
        send_to_telegram(message)

        # التحقق من الرسائل الجديدة
        handle_updates()

        # الانتظار 60 ثانية قبل التكرار
        time.sleep(60)

if __name__ == "__main__":
    logging.info("🚀 Gold Bot التجريبي بدأ!")
    main_loop()
