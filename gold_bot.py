import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters, ContextTypes
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

# --- سحب أسعار الذهب ---
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

# --- سحب أسعار صرف الدولار واليورو مقابل الدينار العراقي ---
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
        if not rates:
            raise ValueError("❌ لم أستطع العثور على أسعار الدولار واليورو")
        return rates
    except Exception as e:
        print("❌ خطأ في جلب أسعار الصرف:", e)
        return None

# --- صياغة الرسالة ---
def format_message():
    gold = get_gold_prices()
    fx = get_fx_rates()

    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    if not gold:
        msg += "❌ خطأ في جلب أسعار الذهب.\n"
    else:
        msg += "💰 أسعار الذهب:\n"
        msg += f"• عيار 24: {gold['gram_24']:.2f} $\n"
        msg += f"• عيار 22: {gold['gram_22']:.2f} $\n"
        msg += f"• عيار 21: {gold['gram_21']:.2f} $\n"
        msg += f"• الأونصة: {gold['ounce']:.2f} $\n"
        if fx:
            msg += f"💰 بالدينار العراقي تقريبًا:\n"
            msg += f"• عيار 24: {(gold['gram_24']*float(fx['USD']['sell'])):.0f} د.ع\n"
            msg += f"• عيار 22: {(gold['gram_22']*float(fx['USD']['sell'])):.0f} د.ع\n"
            msg += f"• عيار 21: {(gold['gram_21']*float(fx['USD']['sell'])):.0f} د.ع\n"

    if not fx:
        msg += "\n❌ خطأ في جلب أسعار الصرف."
    else:
        msg += "\n💱 أسعار العملات مقابل الدينار العراقي:\n"
        for curr in fx:
            msg += f"• {curr} شراء: {fx[curr]['buy']} | بيع: {fx[curr]['sell']}\n"
    return msg

# --- زر حساب الأرباح ---
async def start_profit(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("كم عدد الغرامات التي اشتريتها؟")
    return GRAMS

async def get_grams(update, context: ContextTypes.DEFAULT_TYPE):
    user_data['grams'] = float(update.message.text)
    await update.message.reply_text(f"أرسل المبلغ الإجمالي بالدولار ({user_data['grams']} غرام):")
    return TOTAL_COST

async def get_total_cost(update, context: ContextTypes.DEFAULT_TYPE):
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

async def cancel(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- زر callback handler ---
async def button_handler(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "profit":
        # بدء حساب الأرباح عند الضغط على الزر
        await query.message.reply_text("كم عدد الغرامات التي اشتريتها؟")
        return GRAMS

# --- إرسال الأسعار عند تشغيل البوت ---
async def send_initial_prices(app):
    msg = format_message()
    keyboard = [[InlineKeyboardButton("حساب الأرباح", callback_data="profit")]]
    await app.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=InlineKeyboardMarkup(keyboard))

# --- تشغيل البوت ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Conversation handler لحساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, start_profit)],
        states={
            GRAMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_grams)],
            TOTAL_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_total_cost)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    # إرسال الأسعار عند التشغيل
    await send_initial_prices(app)

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
