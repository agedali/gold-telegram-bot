import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CallbackQueryHandler,
    ConversationHandler, CommandHandler, MessageHandler, filters
)
from datetime import datetime, time
import asyncio
import nest_asyncio
import pytz

nest_asyncio.apply()

# ===== متغيرات البيئة =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# ===== مراحل احتساب الأرباح =====
TYPE, KARAT, AMOUNT, TOTAL_COST = range(4)
user_data = {}

# ===== جلب أسعار الذهب من GOLDAPI =====
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "gram_24": data["price_gram_24k"],
            "gram_22": data["price_gram_22k"],
            "gram_21": data["price_gram_21k"],
            "ounce": data["price"]
        }
    except Exception as e:
        print("❌ خطأ في استدعاء أسعار الذهب:", e)
        return None

# ===== جلب أسعار صرف الدولار واليورو مقابل الدينار العراقي =====
def get_fx_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        rates = {}
        table = soup.find("table")
        if not table:
            return None
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 3:
                currency = cols[0].text.strip()
                buy = cols[1].text.strip()
                sell = cols[2].text.strip()
                if currency in ["USD", "EUR"]:
                    rates[currency] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        print("❌ خطأ في جلب أسعار الصرف:", e)
        return None

# ===== صياغة الرسالة =====
def format_message():
    gold = get_gold_prices()
    fx = get_fx_rates()
    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    if gold:
        msg += "💰 أسعار الذهب بالدولار الأمريكي:\n"
        msg += f"• عيار 24: {gold['gram_24']:.2f} $\n"
        msg += f"• عيار 22: {gold['gram_22']:.2f} $\n"
        msg += f"• عيار 21: {gold['gram_21']:.2f} $\n"
        msg += f"• الأونصة: {gold['ounce']:.2f} $\n\n"
    else:
        msg += "❌ خطأ في جلب أسعار الذهب.\n\n"

    if fx:
        msg += "💱 أسعار العملات مقابل الدينار العراقي:\n"
        for curr in fx:
            msg += f"• {curr} شراء: {fx[curr]['buy']} | بيع: {fx[curr]['sell']}\n"
    else:
        msg += "❌ خطأ في جلب أسعار الصرف.\n"
    return msg

# ===== زر احتساب الأرباح =====
async def start_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="GRAM")],
        [InlineKeyboardButton("مثقال", callback_data="MITQAL")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("اختر نوع الوحدة:", reply_markup=reply_markup)
    return TYPE

async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data['type'] = update.callback_query.data
    keyboard = [
        [InlineKeyboardButton("24", callback_data="24")],
        [InlineKeyboardButton("22", callback_data="22")],
        [InlineKeyboardButton("21", callback_data="21")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("اختر العيار:", reply_markup=reply_markup)
    return KARAT

async def choose_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data['karat'] = int(update.callback_query.data)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(f"أرسل عدد {user_data['type'].lower()} التي اشتريتها:")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data['amount'] = float(update.message.text)
    await update.message.reply_text(f"أرسل المبلغ الإجمالي للشراء بال{user_data['type'].lower()}:")
    return TOTAL_COST

async def get_total_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_cost = float(update.message.text)
    grams_or_mitqal = user_data['amount']
    karat = user_data['karat']
    gold = get_gold_prices()
    if not gold:
        await update.message.reply_text("❌ خطأ في جلب أسعار الذهب، لا يمكن حساب الأرباح.")
        return ConversationHandler.END

    # تحديد سعر الذهب الحالي حسب العيار
    price_per_unit = gold[f'gram_{karat}'] if user_data['type'] == "GRAM" else gold[f'gram_{karat}']*4.25
    profit = (price_per_unit * grams_or_mitqal) - total_cost
    color = "🟢" if profit > 0 else "🔴"
    await update.message.reply_text(f"{color} أرباحك: {profit:.2f} $\n")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# ===== إرسال الأسعار للقناة =====
async def send_prices_job(context: ContextTypes.DEFAULT_TYPE):
    msg = format_message()
    keyboard = [[InlineKeyboardButton("احتساب الأرباح", callback_data="start_profit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# ===== جدولة الرسائل =====
async def schedule_prices(app):
    baghdad_tz = pytz.timezone("Asia/Baghdad")
    for hour in range(10, 18):  # من 10 صباحًا حتى 5 مساءً
        app.job_queue.run_daily(
            send_prices_job,
            time=time(hour, 0, 0, tzinfo=baghdad_tz),
            days=(0, 1, 2, 3, 4, 5, 6)
        )

# ===== تشغيل البوت =====
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # إضافة ConversationHandler لحساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_profit, pattern="start_profit")],
        states={
            TYPE: [CallbackQueryHandler(choose_type)],
            KARAT: [CallbackQueryHandler(choose_karat)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            TOTAL_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_total_cost)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار أول مرة فور التشغيل
    app.job_queue.run_once(send_prices_job, when=0)

    # جدولة الأسعار
    await schedule_prices(app)

    # تشغيل البوت
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
