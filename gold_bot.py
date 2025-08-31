import logging
import os
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")

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
# أمر /start لإرسال الزر
async def start(update, context):
    keyboard = [[InlineKeyboardButton("💵 تحديث سعر الذهب", callback_data="get_price")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("مرحبًا! اضغط الزر للحصول على سعر الذهب الحالي:", reply_markup=reply_markup)

# -----------------------------
# الرد على ضغط الزر
async def button_callback(update, context):
    query = update.callback_query
    await query.answer()  # يجب الرد على الضغط
    prices = generate_fake_prices()
    message = format_price_message(prices)
    await query.edit_message_text(text=message, parse_mode="Markdown")

# -----------------------------
# إرسال تحديث تلقائي كل ساعتين للقناة
async def send_periodic_updates(context: ContextTypes.DEFAULT_TYPE):
    prices = generate_fake_prices()
    message = format_price_message(prices)
    await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

# -----------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="get_price"))

    # تفعيل إرسال التحديث كل ساعتين (7200 ثانية)
    app.job_queue.run_repeating(send_periodic_updates, interval=7200, first=0)

    logging.info("🚀 Gold Bot التجريبي مع زر بدأ!")
    app.run_polling()

if __name__ == "__main__":
    main()
