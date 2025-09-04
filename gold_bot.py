import logging
import os
import requests
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_PRICE = range(4)

# تخزين بيانات المستخدم أثناء الحساب
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

def fetch_gold_prices():
    """جلب الأسعار اللحظية من GoldAPI"""
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        logging.info(f"📡 GoldAPI status: {response.status_code}")
        logging.info(f"📡 GoldAPI raw: {response.text[:200]}")  # نعرض أول 200 حرف للتشخيص

        response.raise_for_status()
        data = response.json()

        prices = {
            "24k": {"gram": data.get("price_gram_24k"), "mithqal": data.get("price_gram_24k") * 5},
            "22k": {"gram": data.get("price_gram_22k"), "mithqal": data.get("price_gram_22k") * 5},
            "21k": {"gram": data.get("price_gram_21k"), "mithqal": data.get("price_gram_21k") * 5},
            "ounce": data.get("price_ounce")  # 👈 أضفنا سعر الأونصة
        }

        logging.info(f"✅ Parsed prices: {prices}")
        return prices

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}")
        return None


def format_prices_message(prices: dict):
    """تنسيق رسالة الأسعار مع التاريخ"""
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")

    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    for karat in ["24k", "22k", "21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"

    # 👇 نعرض سعر الأونصة
    if prices.get("ounce"):
        message += f"🌍 سعر الأونصة العالمية: `{prices['ounce']:.2f}` $\n\n"

    message += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /price"""
    logging.info("⚡ تم استدعاء أمر /price")

    prices = fetch_gold_prices()
    if not prices:
        await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا. تحقق من مفتاح GoldAPI أو جرّب لاحقًا.")
        return

    keyboard = [[InlineKeyboardButton("حساب أرباحك 💰", callback_data="buy")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        format_prices_message(prices),
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


# باقي الكود (buy, cancel, handlers) يبقى نفسه عندك
# ...

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("price", price_command))

    # (تضيف هنا باقي الـ ConversationHandler كما عندك)

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
