import os
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, ConversationHandler, MessageHandler, filters
from datetime import datetime, time

# --- متغيرات البيئة ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# --- مراحل إدخال البيانات ---
GRAMS, TOTAL_COST = range(2)
user_data = {}

# --- سحب أسعار الذهب ---
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        gram = data['gram_24_in_usd']
        return {
            "gram_24": gram,
            "gram_22": gram * 22 / 24,
            "gram_21": gram * 21 / 24,
            "ounce": data['price_ounce_usd']
        }
    except Exception as e:
        print("❌ Error fetching gold prices:", e)
        return None

# --- سحب سعر الدولار واليورو مقابل الدينار العراقي ---
def get_fx_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        rates = {}
        table = soup.find("table")
        if table:
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

# --- حساب الأرباح ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("كم عدد الغرامات التي اشتريتها؟")
    return GRAMS

async def get_grams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_data['grams'] = float(update.message.text)
        await update.message.reply_text(f"أرسل المبلغ الإجمالي بالدولار ({user_data['grams']} غرام):")
        return TOTAL_COST
    except:
        await update.message.reply_text("الرجاء إدخال رقم صحيح.")
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
    except:
        await update.message.reply_text("الرجاء إدخال رقم صحيح.")
        return TOTAL_COST

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- إرسال الأسعار ---
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    msg = format_message()
    await context.bot.send_message(chat_id=CHAT_ID, text=msg)

async def send_prices_first(app):
    msg = format_message()
    await app.bot.send_message(chat_id=CHAT_ID, text=msg)

# --- تشغيل البوت ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            GRAMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_grams)],
            TOTAL_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_total_cost)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار أول مرة
    await send_prices_first(app)

    # جدولة الأسعار كل ساعة من 10 صباحًا حتى 6 مساءً
    for hour in range(10, 19):
        app.job_queue.run_daily(send_prices, time=time(hour,0,0))

    # تشغيل البوت
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()  # لمنع خطأ "event loop already running"
    import asyncio
    asyncio.run(main())
