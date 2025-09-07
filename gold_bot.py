import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from datetime import datetime, time
import nest_asyncio
import asyncio

nest_asyncio.apply()

# المتغيرات
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل ConversationHandler لحساب الأرباح
UNIT, AMOUNT, TOTAL = range(3)
user_data = {}

# --- جلب أسعار الذهب ---
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "24": data.get("price_gram_24k"),
            "22": data.get("price_gram_22k"),
            "21": data.get("price_gram_21k"),
            "ounce": data.get("price")
        }
    except Exception as e:
        print("❌ خطأ في استدعاء أسعار الذهب:", e)
        return None

# --- جلب أسعار الدولار واليورو مقابل الدينار العراقي ---
def get_fx_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        rates = {}
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
        print("❌ لم أستطع العثور على أسعار الدولار واليورو:", e)
        return None

# --- صياغة رسالة الأسعار ---
def format_message():
    gold = get_gold_prices()
    fx = get_fx_rates()
    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    if gold:
        msg += "💰 أسعار الذهب بالدولار الأمريكي:\n"
        msg += f"• عيار 24: {gold['24']:.2f} $\n"
        msg += f"• عيار 22: {gold['22']:.2f} $\n"
        msg += f"• عيار 21: {gold['21']:.2f} $\n"
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

# --- بدء حساب الأرباح ---
async def start_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="gram")],
        [InlineKeyboardButton("مثقال", callback_data="mithqal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("اختر الوحدة:", reply_markup=reply_markup)
    return UNIT

async def get_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_data['unit'] = query.data
    await query.answer()
    await query.edit_message_text(f"أدخل عدد {user_data['unit']}:")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data['amount'] = float(update.message.text)
    await update.message.reply_text(f"أدخل المبلغ الكلي للشراء ({user_data['unit']}):")
    return TOTAL

async def get_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_cost = float(update.message.text)
    amount = user_data['amount']
    unit = user_data['unit']
    gold = get_gold_prices()
    if not gold:
        await update.message.reply_text("❌ خطأ في جلب أسعار الذهب.")
        return ConversationHandler.END
    # تحويل الوحدة إلى غرام إذا كانت مثقال
    if unit == "mithqal":
        amount_in_grams = amount * 4.25
    else:
        amount_in_grams = amount
    current_price = gold['24']  # عيار 24
    profit = (current_price * amount_in_grams) - total_cost
    color = "🟢" if profit > 0 else "🔴"
    await update.message.reply_text(f"{color} أرباحك: {profit:.2f} $")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- إرسال الأسعار للبوت والقناة ---
async def send_prices(bot):
    msg = format_message()
    keyboard = [[InlineKeyboardButton("حساب الأرباح", callback_data="profit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# --- جدولة الرسائل ---
async def schedule_prices(app):
    for hour in range(10, 19):  # من 10 صباحًا حتى 6 مساءً
        app.job_queue.run_daily(send_prices, time=time(hour, 0, 0), days=(0,1,2,3,4,5,6), context=app.bot)

# --- البرنامج الرئيسي ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_profit, pattern="profit")],
        states={
            UNIT: [CallbackQueryHandler(get_unit)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_total)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار عند تشغيل البوت لأول مرة
    await send_prices(app.bot)

    # جدولة الأسعار
    await schedule_prices(app)

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
