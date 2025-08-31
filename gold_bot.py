import logging
import os
import random
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_PRICES = {
    "ounce_usd": 1950.50,
    "gram_usd": 62.73,
    "gram_iqd": 915000
}

# -----------------------------
def generate_fake_prices():
    prices = {}
    prices["ounce_usd"] = round(BASE_PRICES["ounce_usd"] + random.uniform(-5, 5), 2)
    prices["gram_usd"] = round(prices["ounce_usd"] / 31.1035, 2)
    prices["gram_iqd"] = int(prices["gram_usd"] * 14580)
    return prices

def format_price_message(prices: dict):
    message = (
        "💰 **تحديث أسعار الذهب** 💰\n\n"
        f"🔸 **الأونصة:** `{prices['ounce_usd']:.2f}` $\n"
        f"🔸 **الغرام بالدولار:** `{prices['gram_usd']:.2f}` $\n"
        f"🔸 **الغرام بالدينار العراقي:** `{prices['gram_iqd']:,}` IQD\n\n"
        "_اضغط الزر للحصول على تحديث فوري_"
    )
    return message

# -----------------------------
async def start(update, context):
    keyboard = [[InlineKeyboardButton("💵 تحديث سعر الذهب", callback_data="get_price")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("مرحبًا! اضغط الزر للحصول على سعر الذهب الحالي:", reply_markup=reply_markup)

# -----------------------------
async def button_callback(update, context):
    query = update.callback_query
    await query.answer()
    prices = generate_fake_prices()
    message = format_price_message(prices)
    await query.edit_message_text(text=message, parse_mode="Markdown")

# -----------------------------
async def periodic_updates(app):
    while True:
        prices = generate_fake_prices()
        message = format_price_message(prices)
        await app.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
        logging.info("📩 تم إرسال تحديث تلقائي للقناة")
        await asyncio.sleep(7200)  # كل ساعتين

# -----------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="get_price"))

    # تشغيل التحديث التلقائي في الخلفية
    asyncio.create_task(periodic_updates(app))

    logging.info("🚀 Gold Bot بدأ مع زر وتحديث تلقائي")
    app.run_polling()

if __name__ == "__main__":
    main()
