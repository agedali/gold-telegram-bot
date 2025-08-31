import logging
import os
import random
from telegram.ext import ApplicationBuilder, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")

BASE_PRICES = {
    "ounce_usd": 1950.50,
    "gram_usd": 62.73,
    "gram_iqd": 915000
}

def generate_fake_prices():
    prices = {}
    prices["ounce_usd"] = round(BASE_PRICES["ounce_usd"] + random.uniform(-5, 5), 2)
    prices["gram_usd"] = round(prices["ounce_usd"] / 31.1035, 2)
    prices["gram_iqd"] = int(prices["gram_usd"] * 14580)
    return prices

def format_price_message(prices: dict):
    return (
        "💰 **تحديث أسعار الذهب** 💰\n\n"
        f"🔸 **الأونصة:** `{prices['ounce_usd']:.2f}` $\n"
        f"🔸 **الغرام بالدولار:** `{prices['gram_usd']:.2f}` $\n"
        f"🔸 **الغرام بالدينار العراقي:** `{prices['gram_iqd']:,}` IQD\n"
    )

async def send_periodic_update(context: ContextTypes.DEFAULT_TYPE):
    prices = generate_fake_prices()
    message = format_price_message(prices)
    await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
    logging.info("📩 تم إرسال تحديث تلقائي للقناة")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # تشغيل التحديث التلقائي كل ساعتين باستخدام JobQueue
    app.job_queue.run_repeating(send_periodic_update, interval=7200, first=0)

    logging.info("🚀 Gold Bot بدأ ويعمل على إرسال الأسعار كل ساعتين")
    app.run_polling()
