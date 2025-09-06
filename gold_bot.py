import logging
import os
import requests
from datetime import datetime, time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --------------- إعداد اللوج ---------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --------------- مفاتيح البيئة ---------------
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# --------------- مراحل حساب الأرباح ---------------
BUY_KARAT, BUY_UNIT, BUY_AMOUNT = range(3)
user_buy_data = {}

days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --------------- جلب أسعار الذهب ---------------
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        gram_24k = data.get("price_gram_24k")
        gram_22k = data.get("price_gram_22k")
        gram_21k = data.get("price_gram_21k")
        ounce = data.get("price_ounce")
        return {
            "24k": {"gram": gram_24k, "mithqal": gram_24k * 5},
            "22k": {"gram": gram_22k, "mithqal": gram_22k * 5},
            "21k": {"gram": gram_21k, "mithqal": gram_21k * 5},
            "ounce": ounce,
        }
    except Exception as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --------------- جلب أسعار الدولار واليورو مقابل الدينار العراقي ---------------
def fetch_currency_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        usd_buy = float(data['USD']['Buy'])
        usd_sell = float(data['USD']['Sell'])
        eur_buy = float(data['EUR']['Buy'])
        eur_sell = float(data['EUR']['Sell'])
        return {"USD": {"buy": usd_buy, "sell": usd_sell}, "EUR": {"buy": eur_buy, "sell": eur_sell}}
    except Exception as e:
        logging.error(f"❌ Error fetching currency rates: {e}")
        return None

# --------------- تنسيق رسالة الأسعار ---------------
def format_prices_message(prices, currency_rates, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = ""
    if special_msg:
        message += f"{special_msg}\n\n"
    message += f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    for karat in ["24k", "22k", "21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    message += f"🔹 الأونصة: `{prices['ounce']:.2f}` $\n\n"
    if currency_rates:
        message += f"💵 الدولار مقابل الدينار العراقي: شراء `{currency_rates['USD']['buy']}` | بيع `{currency_rates['USD']['sell']}`\n"
        message += f"💶 اليورو مقابل الدينار العراقي: شراء `{currency_rates['EUR']['buy']}` | بيع `{currency_rates['EUR']['sell']}`\n\n"
    message += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message

# --------------- إرسال الأسعار ---------------
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    currency_rates = fetch_currency_rates()
    if not prices:
        return
    message = format_prices_message(prices, currency_rates)
    keyboard = [[InlineKeyboardButton("حساب أرباحك 💰", callback_data="buy")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown", reply_markup=reply_markup)

# --------------- حساب الأرباح ---------------
async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("24k", callback_data="24k"),
         InlineKeyboardButton("22k", callback_data="22k"),
         InlineKeyboardButton("21k", callback_data="21k")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر عيار الذهب الذي اشتريته:", reply_markup=reply_markup)
    return BUY_KARAT

async def buy_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id] = {"karat": query.data}
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="gram"),
         InlineKeyboardButton("مثقال", callback_data="mithqal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر الوحدة (غرام أو مثقال):", reply_markup=reply_markup)
    return BUY_UNIT

async def buy_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id]["unit"] = query.data
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) بالدولار:")
    return BUY_AMOUNT

async def buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",", "."))
        data = user_buy_data[user_id]
        unit_count = 1 if data["unit"] == "gram" else 5
        unit_price = total_price / unit_count
        prices = fetch_gold_prices()
        current_price = prices[data["karat"]][data["unit"]]
        profit = (current_price - unit_price) * unit_count
        color = "🟢 ربح" if profit >= 0 else "🔴 خسارة"
        await update.message.reply_text(
            f"💰 نتائج حساب أرباحك:\n"
            f"عيار الذهب: {data['karat']}\n"
            f"الوحدة: {data['unit']}\n"
            f"الكمية: {unit_count}\n"
            f"السعر الإجمالي: {total_price} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{color}: {profit:.2f} $"
        )
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except Exception:
        await update.message.reply_text("⚠️ الرجاء إدخال رقم صالح")
        return BUY_AMOUNT

# --------------- التشغيل الرئيسي ---------------
if __name__ == "__main__":
    from telegram.ext import ConversationHandler

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # إضافة حساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_amount)],
        },
        fallbacks=[],
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار أول مرة عند التشغيل
    async def first_send():
        await send_prices(ContextTypes.DEFAULT_TYPE(application=app, job=None))
    import asyncio
    asyncio.run(first_send())

    # إرسال الأسعار كل ساعة من 10 صباحًا حتى 10 مساءً
    for h in range(10, 23):
        app.job_queue.run_daily(send_prices, time=time(hour=h, minute=0))

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
