import requests
import time
import logging
import os

# إعداد لوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح من الـ GitHub Secrets أو البيئة
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDPRICEZ_API_KEY = os.getenv("GOLDPRICEZ_API_KEY")
# رابط API الذهب
API_URL = f"https://goldpricez.com/api/rates/currency/usd/measure/all?api_key={GOLDPRICEZ_API_KEY}"


def get_spot_xau_usd():
    """
    تجيب سعر الأونصة بالدولار
    """
    r = requests.get(API_URL)
    r.raise_for_status()

    try:
        data = r.json()
        logging.info(f"✅ Parsed JSON: {data}")

        if "ounce_price_usd" in data:
            return float(data["ounce_price_usd"])
        elif "ounce" in data:
            return float(data["ounce"])
        else:
            raise RuntimeError("❌ مفتاح السعر غير موجود في الـ JSON")

    except Exception as e:
        logging.error(f"🔎 Raw response: {r.text}")
        raise RuntimeError(f"❌ Unexpected API response: {r.text}") from e


def send_to_telegram(message: str):
    """
    ترسل رسالة إلى تيليغرام
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=payload)
    if r.status_code != 200:
        logging.error(f"❌ Telegram error: {r.text}")
    else:
        logging.info("📩 Message sent to Telegram!")


def main():
    logging.info("🚀 Starting Gold Bot...")

    try:
        ounce_usd = get_spot_xau_usd()
        message = f"💰 **سعر الذهب اليوم**\n\n🔸 الأونصة: `{ounce_usd:.2f}` دولار"
        logging.info(message)
        send_to_telegram(message)

    except Exception as e:
        logging.error(f"❌ Error fetching gold price: {e}")


if __name__ == "__main__":
    # تشغيل لمرة واحدة
    main()

    # أو للتحديث كل 10 دقائق مثلاً
    # while True:
    #     main()
    #     time.sleep(600)
