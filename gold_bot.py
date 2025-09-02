import logging
import os
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @channelusername أو -100xxxxxxxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")


def fetch_gold_prices():
    """تجلب أسعار الذهب من GoldAPI"""
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # أسعار الغرام
        gram_24k = data.get("price_gram_24k")
        gram_22k = data.get("price_gram_22k")
        gram_21k = data.get("price_gram_21k")

        # حساب المثقال (5 غرام)
        mithqal_24k = gram_24k * 5
        mithqal_22k = gram_22k * 5
        mithqal_21k = gram_21k * 5

        return {
            "24k": {"gram": gram_24k, "mithqal": mithqal_24k},
            "22k": {"gram": gram_22k, "mithqal": mithqal_22k},
            "21k": {"gram": gram_21k, "mithqal": mithqal_21k},
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None


def format_message(prices: dict):
    """تنسيق الرسالة بشكل احترافي"""
    return (
        "💰 **أسعار الذهب اليوم** 💰\n\n"
        f"🔹 **عيار 24**:\n"
        f"   - الغرام: `{prices['24k']['gram']:.2f}` $\n"
        f"   - المثقال: `{prices['24k']['mithqal']:.2f}` $\n\n"
        f"🔹 **عيار 22**:\n"
        f"   - الغرام: `{prices['22k']['gram']:.2f}` $\n"
        f"   - المثقال: `{prices['22k']['mithqal']:.2f}` $\n\n"
        f"🔹 **عيار 21**:\n"
        f"   - الغرام: `{prices['21k']['gram']:.2f}` $\n"
        f"   - المثقال: `{prices['21k']['mithqal']:.2f}` $\n"
    )


async def send_gold_prices(context: ContextTypes.DEFAULT_TYPE):
    """إرسال الرسالة للقناة"""
    prices = fetch_gold_prices()
    if prices:
        message = format_message(prices)
        await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
        logging.info("📩 تم إرسال أسعار الذهب إلى القناة")


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /price لتحديث فوري مع أزرار"""
    keyboard = [
        [
            InlineKeyboardButton("عيار 24", callback_data="24k"),
            InlineKeyboardButton("عيار 22", callback_data="22k"),
            InlineKeyboardButton("عيار 21", callback_data="21k"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر العيار لعرض السعر:", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغط الأزرار"""
    query = update.callback_query
    await query.answer()

    prices = fetch_gold_prices()
    if not prices:
        await query.edit_message_text("⚠️ تعذر جلب الأسعار حالياً.")
        return

    choice = query.data
    selected = prices[choice]
    message = (
        f"💰 **سعر الذهب - {choice.upper()}** 💰\n\n"
        f"🔹 الغرام: `{selected['gram']:.2f}` $\n"
        f"🔹 المثقال: `{selected['mithqal']:.2f}` $\n"
    )

    await query.edit_message_text(message, parse_mode="Markdown")


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # إرسال تحديث تلقائي كل ساعتين
    app.job_queue.run_repeating(send_gold_prices, interval=7200, first=0)

    logging.info("🚀 Gold Bot بدأ ويعمل مع تحديث تلقائي كل ساعتين وأمر /price")
    app.run_polling()
