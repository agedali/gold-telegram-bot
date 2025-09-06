import logging
import os
import requests
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    JobQueue
)

# --- إعداد اللوج ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- مفاتيح البيئة ---
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # قناة أو شخص
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# --- مراحل حساب الأرباح ---
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_PRICE = range(4)
user_buy_data = {}

# --- خريطة الأيام بالعربي ---
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- جلب أسعار الذهب ---
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "24k": {"gram": data.get("price_gram_24k"), "mithqal": data.get("price_gram_24k")*5},
            "22k": {"gram": data.get("price_gram_22k"), "mithqal": data.get("price_gram_22k")*5},
            "21k": {"gram": data.get("price_gram_21k"), "mithqal": data.get("price_gram_21k")*5},
            "ounce": data.get("price_ounce")
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- جلب أسعار الدولار واليورو مقابل الدينار العراقي ---
def fetch_currency_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return {
            "USD_buy": data["USD"]["buy"],
            "USD_sell": data["USD"]["sell"],
            "EUR_buy": data["EUR"]["buy"],
            "EUR_sell": data["EUR"]["sell"]
        }
    except:
        return None

# --- تنسيق رسالة الأسعار ---
def format_prices_message(prices, currency_rates=None, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    if special_msg:
        message += f"{special_msg}\n\n"
    for karat in ["24k","22k","21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n"
    message += f"\n🔹 الأونصة: `{prices['ounce']:.2f}` $\n"
    
    if currency_rates:
        message += "\n💵 أسعار العملات مقابل الدينار العراقي:\n"
        message += f"   - الدولار: شراء `{currency_rates['USD_buy']}` | بيع `{currency_rates['USD_sell']}`\n"
        message += f"   - اليورو: شراء `{currency_rates['EUR_buy']}` | بيع `{currency_rates['EUR_sell']}`\n"

    message += "\n💎 لحساب أرباحك استخدم الأزرار أدناه"
    return message

# --- إرسال الأسعار للقناة ---
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    currency_rates = fetch_currency_rates()
    if prices:
        msg = format_prices_message(prices, currency_rates)
        await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

# --- إرسال الرسائل المجدولة من 10 صباحًا إلى 6 مساءً ---
def schedule_jobs(app):
    job_queue = app.job_queue
    for hour in range(10, 19):  # من 10 صباحًا حتى 6 مساءً
        job_queue.run_daily(send_prices, time=datetime.strptime(f"{hour}:00", "%H:%M").time())

# --- حساب الأرباح ---
async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("24k", callback_data="24k"),
         InlineKeyboardButton("22k", callback_data="22k"),
         InlineKeyboardButton("21k", callback_data="21k")]
    ]
    await query.edit_message_text("اختر عيار الذهب الذي اشتريته:", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_KARAT

async def buy_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id] = {"karat": query.data}
    keyboard = [[InlineKeyboardButton("غرام", callback_data="gram"),
                 InlineKeyboardButton("مثقال", callback_data="mithqal")]]
    await query.edit_message_text("اختر الوحدة (غرام أو مثقال):", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_UNIT

async def buy_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id]["unit"] = query.data
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) الذي تم شراؤه بالدولار:")
    return BUY_PRICE

async def buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",","."))  
        data = user_buy_data[user_id]
        unit_amount = data.get("amount", 1)
        price_per_unit = total_price / unit_amount
        data["price"] = price_per_unit

        # الحصول على السعر الحالي
        prices = fetch_gold_prices()
        current_price = prices[data["karat"]][data["unit"]]
        profit = (current_price - price_per_unit) * unit_amount

        # رسالة النتائج مع اللون الأخضر/الأحمر
        color = "🟢" if profit >=0 else "🔴"
        await update.message.reply_text(
            f"{color} نتائج حساب أرباحك:\n"
            f"عيار الذهب: {data['karat']}\n"
            f"الوحدة: {data['unit']}\n"
            f"الكمية: {unit_amount}\n"
            f"سعر الشراء لكل وحدة: {price_per_unit:.2f} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"الربح/الخسارة: {profit:.2f} $"
        )
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح.")
        return BUY_PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_buy_data.pop(update.message.from_user.id, None)
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# --- التطبيق الرئيسي ---
app = ApplicationBuilder().token(BOT_TOKEN).build()

# إضافة محادثة حساب الأرباح
conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
    states={
        BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
        BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
        BUY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_price)],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel)]
)
app.add_handler(conv_handler)

# --- إرسال الأسعار أول مرة ---
async def first_send():
    prices = fetch_gold_prices()
    currency_rates = fetch_currency_rates()
    if prices:
        msg = format_prices_message(prices, currency_rates, special_msg="تم فتح بورصة العراق")
        await app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

# --- تشغيل البوت ---
import asyncio
async def main():
    # إرسال الأسعار فورًا عند التشغيل
    await first_send()
    # جدولة الرسائل
    schedule_jobs(app)
    # تشغيل البوت
    await app.run_polling()

asyncio.run(main())
