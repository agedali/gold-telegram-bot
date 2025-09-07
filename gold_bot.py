import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from datetime import datetime

# --- المتغيرات ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

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
            "24k": data.get("price_gram_24k"),
            "22k": data.get("price_gram_22k"),
            "21k": data.get("price_gram_21k"),
            "ounce": data.get("price"),
            "ask": data.get("ask"),
            "bid": data.get("bid")
        }
    except Exception as e:
        print("❌ خطأ في استدعاء أسعار الذهب", e)
        return None

# --- سحب سعر الدولار واليورو مقابل الدينار ---
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
        print("❌ لم أستطع العثور على أسعار الدولار واليورو", e)
        return None

# --- صياغة الرسالة ---
def format_message():
    gold = get_gold_prices()
    fx = get_fx_rates()
    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    if gold:
        msg += "💰 أسعار الذهب:\n"
        msg += f"• عيار 24: {gold['24k']} $ | شراء: {gold['bid']} $ | بيع: {gold['ask']} $\n"
        msg += f"• عيار 22: {gold['22k']} $\n"
        msg += f"• عيار 21: {gold['21k']} $\n"
        msg += f"• الأونصة: {gold['ounce']} $\n\n"
    else:
        msg += "❌ خطأ في جلب أسعار الذهب.\n\n"

    if fx:
        msg += "💱 أسعار العملات مقابل الدينار العراقي:\n"
        for curr in fx:
            msg += f"• {curr}: شراء: {fx[curr]['buy']} | بيع: {fx[curr]['sell']}\n"
    else:
        msg += "❌ خطأ في جلب أسعار الصرف.\n"

    return msg

# --- زر حساب الأرباح ---
async def start_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("حساب الأرباح", callback_data="profit")]
    ]
    await update.message.reply_text(format_message(), reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "profit":
        await query.message.reply_text("كم عدد الغرامات التي اشتريتها؟")
        return GRAMS
    return ConversationHandler.END

async def get_grams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_data['grams'] = float(update.message.text)
        await update.message.reply_text(f"أرسل المبلغ الإجمالي بالدولار ({user_data['grams']} غرام):")
        return TOTAL_COST
    except:
        await update.message.reply_text("أدخل رقم صحيح.")
        return GRAMS

async def get_total_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        total_cost = float(update.message.text)
        grams = user_data['grams']
        price_per_gram = total_cost / grams
        gold = get_gold_prices()
        if gold:
            current_price = gold['24k']
            profit = (current_price - price_per_gram) * grams
            color = "🟢" if profit > 0 else "🔴"
            await update.message.reply_text(f"{color} أرباحك: {profit:.2f} $")
        else:
            await update.message.reply_text("❌ لا أستطيع جلب أسعار الذهب حالياً.")
        return ConversationHandler.END
    except:
        await update.message.reply_text("أدخل رقم صحيح.")
        return TOTAL_COST

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- تشغيل البوت ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

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

    # إرسال الأسعار أول مرة عند التشغيل
    await start_profit(update=await app.bot.get_updates()[0], context=None)

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    asyncio.run(main())
