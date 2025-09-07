import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from datetime import datetime, time
import asyncio

# --- متغيرات البيئة ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# --- مراحل حساب الأرباح ---
CHOICE_TYPE, CHOICE_METAL, INPUT_AMOUNT, INPUT_COST = range(4)
user_data = {}

# --- سحب أسعار الذهب ---
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "gram_24": data.get("price_gram_24k", 0),
            "gram_22": data.get("price_gram_22k", 0),
            "gram_21": data.get("price_gram_21k", 0),
            "ounce": data.get("price", 0)
        }
    except Exception as e:
        print("❌ Error fetching gold prices:", e)
        return None

# --- سحب أسعار الدولار واليورو مقابل الدينار العراقي ---
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
        print("❌ Error fetching FX rates:", e)
        return None

# --- صياغة رسالة الأسعار ---
def format_message():
    gold = get_gold_prices()
    fx = get_fx_rates()
    if not gold:
        return "❌ خطأ في جلب أسعار الذهب."
    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    msg += "💰 أسعار الذهب بالدولار الأمريكي:\n"
    msg += f"• عيار 24: {gold['gram_24']:.2f} $\n"
    msg += f"• عيار 22: {gold['gram_22']:.2f} $\n"
    msg += f"• عيار 21: {gold['gram_21']:.2f} $\n"
    msg += f"• الأونصة: {gold['ounce']:.2f} $\n\n"
    if fx:
        msg += "💱 أسعار العملات مقابل الدينار العراقي:\n"
        for curr in fx:
            msg += f"• {curr} شراء: {fx[curr]['buy']} | بيع: {fx[curr]['sell']}\n"
    else:
        msg += "❌ خطأ في جلب أسعار الصرف."
    return msg

# --- إرسال الأسعار مع زر حساب الأرباح ---
async def send_prices(bot):
    msg = format_message()
    keyboard = [[InlineKeyboardButton("💰 حساب الأرباح", callback_data="profit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# --- خطوات حساب الأرباح ---
async def profit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="gram")],
        [InlineKeyboardButton("مثقال", callback_data="mithqal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("اختر الوحدة:", reply_markup=reply_markup)
    return CHOICE_TYPE

async def choice_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_data['type'] = query.data
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("24", callback_data="24")],
        [InlineKeyboardButton("22", callback_data="22")],
        [InlineKeyboardButton("21", callback_data="21")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("اختر عيار الذهب:", reply_markup=reply_markup)
    return CHOICE_METAL

async def choice_metal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_data['metal'] = int(query.data)
    await query.answer()
    await query.message.reply_text(f"أدخل الكمية ({user_data['type']}):")
    return INPUT_AMOUNT

async def input_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_data['amount'] = float(update.message.text)
        await update.message.reply_text("أدخل المبلغ الكلي للشراء بالدولار:")
        return INPUT_COST
    except:
        await update.message.reply_text("الرجاء إدخال رقم صالح للكمية:")
        return INPUT_AMOUNT

async def input_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_data['total_cost'] = float(update.message.text)
        # حساب الربح
        gold = get_gold_prices()
        if not gold:
            await update.message.reply_text("❌ خطأ في جلب أسعار الذهب حالياً.")
            return ConversationHandler.END
        price_per_gram = gold[f"gram_{user_data['metal']}"] if user_data['type']=="gram" else gold[f"gram_{user_data['metal']}"]*1.8  # تحويل المثقال إلى غرام تقريبا
        profit = (price_per_gram * user_data['amount'] - user_data['total_cost'])
        color = "🟢" if profit > 0 else "🔴"
        await update.message.reply_text(f"{color} أرباحك: {profit:.2f} $")
        return ConversationHandler.END
    except:
        await update.message.reply_text("الرجاء إدخال رقم صالح للمبلغ الكلي:")
        return INPUT_COST

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- جدولة الإرسال اليومي ---
async def schedule_prices(app):
    for hour in range(10, 19):
        app.job_queue.run_daily(send_prices, time=time(hour,0,0), days=(0,1,2,3,4,5,6), context=app.bot)

# --- تشغيل البوت ---
async def main():
    import nest_asyncio
    nest_asyncio.apply()
    
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(profit_start, pattern="profit")],
        states={
            CHOICE_TYPE: [CallbackQueryHandler(choice_type)],
            CHOICE_METAL: [CallbackQueryHandler(choice_metal)],
            INPUT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_amount)],
            INPUT_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_cost)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار أول مرة عند التشغيل
    await send_prices(app.bot)

    # جدولة الرسائل
    await schedule_prices(app)

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
