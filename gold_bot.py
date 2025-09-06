import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
from datetime import datetime, time
import asyncio
import nest_asyncio

nest_asyncio.apply()

# --- متغيرات البيئة ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# --- مراحل إدخال البيانات ---
GRAMS, TOTAL_COST = range(2)
user_data = {}

# --- جلب أسعار الذهب بالدولار ---
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # 👇 نطبع الرد لمعرفة المفاتيح
        print("📊 GOLDAPI Response:", data)

        # بعض الـ API يرسل السعر بالمفتاح "price"
        gram = data.get("price_gram_usd", data.get("price"))
        if not gram:
            raise KeyError("price_gram_usd or price not found in API response")

        return {
            "gram_24": gram,
            "gram_22": gram * 22 / 24,
            "gram_21": gram * 21 / 24,
            "ounce": data.get("price", 0.0)
        }
    except Exception as e:
        print("❌ Error fetching gold prices:", e)
        return None

# --- جلب سعر الدولار واليورو مقابل الدينار العراقي ---
def get_fx_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        rates = {}
        table = soup.find("table")
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
        return {}

# --- صياغة الرسالة ---
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
    return msg

# --- إرسال الأسعار مع زر حساب الأرباح ---
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    msg = format_message()
    keyboard = [[InlineKeyboardButton("حساب الأرباح", callback_data="calculate_profit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# --- عند تشغيل البوت: إرسال الأسعار مباشرة ---
async def send_initial_prices(app):
    msg = format_message()
    keyboard = [[InlineKeyboardButton("حساب الأرباح", callback_data="calculate_profit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await app.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# --- التعامل مع ضغط الزر ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="🔹 الرجاء إدخال عدد الغرامات التي اشتريتها:")
    return GRAMS

# --- حساب الأرباح ---
async def get_grams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_data['grams'] = float(update.message.text)
        await update.message.reply_text(f"أرسل المبلغ الإجمالي بالدولار ({user_data['grams']} غرام):")
        return TOTAL_COST
    except ValueError:
        await update.message.reply_text("❌ يجب إدخال رقم صحيح للغرامات.")
        return GRAMS

async def get_total_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        total_cost = float(update.message.text)
        grams = user_data['grams']
        price_per_gram = total_cost / grams
        gold = get_gold_prices()
        if gold:
            current_price = gold['gram_24']
            profit = (current_price - price_per_gram) * grams
            color = "🟢" if profit > 0 else "🔴"
            await update.message.reply_text(f"{color} أرباحك: {profit:.2f} $")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ يجب إدخال رقم صحيح للمبلغ.")
        return TOTAL_COST

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- جدولة إرسال الأسعار كل ساعة من 10 صباحًا حتى 6 مساءً ---
async def schedule_prices(app):
    for hour in range(10, 19):
        app.job_queue.run_daily(send_prices, time=time(hour, 0, 0), days=(0,1,2,3,4,5,6))

# --- تشغيل البوت ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="calculate_profit")],
        states={
            GRAMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_grams)],
            TOTAL_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_total_cost)],
        },
        fallbacks=[MessageHandler(filters.Regex('^إلغاء$'), cancel)]
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار أول مرة عند تشغيل البوت
    await send_initial_prices(app)

    # جدولة الرسائل
    await schedule_prices(app)

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
