import logging
import os
import requests
from datetime import datetime, time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bs4 import BeautifulSoup  # لسحب أسعار الدولار واليورو

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # القناة أو البوت
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_TOTAL_PRICE = range(4)
user_buy_data = {}

# خريطة الأيام بالعربي
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
    except Exception as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- جلب أسعار الدولار واليورو مقابل الدينار العراقي ---
def fetch_currency_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        r = requests.get(url)
        soup = BeautifulSoup(r.content, "html.parser")
        table = soup.find("table")
        rates = {}
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            currency = cols[0].text.strip()
            buy = cols[1].text.strip()
            sell = cols[2].text.strip()
            if currency in ["دولار أمريكي", "يورو"]:
                rates[currency] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        logging.error(f"❌ Error fetching currency rates: {e}")
        return None

# --- تنسيق رسالة الأسعار ---
def format_prices_message(prices, currency_rates, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = ""
    if special_msg:
        message += f"💹 {special_msg}\n\n"
    message += f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    for karat in ["24k", "22k", "21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    message += f"🔸 الأونصة: `{prices['ounce']:.2f}` $\n\n"

    if currency_rates:
        message += "💵 أسعار العملات مقابل الدينار العراقي:\n"
        for cur, val in currency_rates.items():
            message += f"   - {cur}: شراء `{val['buy']}` | بيع `{val['sell']}`\n"
    return message

# --- إرسال الأسعار ---
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    currency_rates = fetch_currency_rates()
    if not prices:
        logging.error("⚠️ تعذر جلب أسعار الذهب")
        return
    msg = format_prices_message(prices, currency_rates)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

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
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="gram"),
         InlineKeyboardButton("مثقال", callback_data="mithqal")]
    ]
    await query.edit_message_text("اختر الوحدة (غرام أو مثقال):", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_UNIT

async def buy_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id]["unit"] = query.data
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) بالدولار:")
    return BUY_TOTAL_PRICE

async def buy_total_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",", "."))
        data = user_buy_data[user_id]
        amount = float(input("ادخل عدد الوحدات: "))  # بدلاً من ذلك يمكن تعديل البوت لإرسال الكمية
        data["amount"] = amount
        price_per_unit = total_price / amount
        data["price_per_unit"] = price_per_unit

        prices = fetch_gold_prices()
        current_price = prices[data["karat"]][data["unit"]]
        profit = (current_price - price_per_unit) * amount

        color = "🟢 ربح" if profit >= 0 else "🔴 خسارة"
        await update.message.reply_text(
            f"💰 نتائج حساب أرباحك:\n"
            f"عيار الذهب: {data['karat']}\n"
            f"الوحدة: {data['unit']}\n"
            f"الكمية: {amount}\n"
            f"سعر الوحدة: {price_per_unit:.2f} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{color}: {profit:.2f} $"
        )
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text("⚠️ حدث خطأ. الرجاء التأكد من البيانات.")
        logging.error(e)
        return BUY_TOTAL_PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_buy_data.pop(user_id, None)
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# ------------------- MAIN -------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

# إضافة حساب الأرباح
conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
    states={
        BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
        BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
        BUY_TOTAL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_total_price)],
    },
    fallbacks=[MessageHandler(filters.Regex("cancel"), cancel)],
)
app.add_handler(conv_handler)

# --- جدولة الرسائل ---
from telegram.ext import JobQueue

job_queue = app.job_queue
for hour in range(10, 19):
    job_queue.run_daily(send_prices, time=time(hour, 0, 0))

# --- إرسال الرسالة الأولى عند التشغيل ---
async def first_send():
    prices = fetch_gold_prices()
    currency_rates = fetch_currency_rates()
    if prices:
        msg = format_prices_message(prices, currency_rates, special_msg="تم فتح بورصة العراق")
        await app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

# --- تشغيل البوت ---
async def main():
    await first_send()
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.idle()

import asyncio
asyncio.run(main())
