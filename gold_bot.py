import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from datetime import datetime, time
import asyncio
import nest_asyncio

nest_asyncio.apply()

# ------------------- متغيرات البيئة -------------------
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# ------------------- مراحل احتساب الأرباح -------------------
UNIT, KARAT, QUANTITY, TOTAL_COST = range(4)
user_data = {}

# ------------------- سحب أسعار الذهب -------------------
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "gram_24": data["price_gram_24k"],
            "gram_22": data["price_gram_22k"],
            "gram_21": data["price_gram_21k"],
            "ounce": data.get("price", 0),
        }
    except Exception as e:
        print("❌ Error fetching gold prices:", e)
        return None

# ------------------- سحب أسعار الدولار واليورو مقابل الدينار العراقي -------------------
def get_fx_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        rates = {}
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 3:
                curr = cols[0].text.strip()
                buy = cols[1].text.strip()
                sell = cols[2].text.strip()
                if curr in ["USD", "EUR"]:
                    rates[curr] = {"buy": buy, "sell": sell}
        if not rates:
            return None
        return rates
    except Exception as e:
        print("❌ Error fetching FX rates:", e)
        return None

# ------------------- صياغة الرسالة -------------------
def format_message():
    gold = get_gold_prices()
    fx = get_fx_rates()
    if not gold:
        return "❌ خطأ في جلب أسعار الذهب."
    if not fx:
        return "❌ خطأ في جلب أسعار الصرف."

    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    msg += "💰 أسعار الذهب بالدولار الأمريكي:\n"
    msg += f"• عيار 24: {gold['gram_24']:.2f} $\n"
    msg += f"• عيار 22: {gold['gram_22']:.2f} $\n"
    msg += f"• عيار 21: {gold['gram_21']:.2f} $\n"
    msg += f"• الأونصة: {gold['ounce']:.2f} $\n\n"

    msg += "💱 أسعار العملات مقابل الدينار العراقي:\n"
    for curr in fx:
        msg += f"• {curr} شراء: {fx[curr]['buy']} | بيع: {fx[curr]['sell']}\n"

    return msg

# ------------------- بدء احتساب الأرباح -------------------
async def start_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="unit_gram")],
        [InlineKeyboardButton("مثقال", callback_data="unit_mithqal")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر الوحدة:", reply_markup=reply_markup)
    return UNIT

async def choose_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data["unit"] = "gram" if query.data == "unit_gram" else "mithqal"

    keyboard = [
        [InlineKeyboardButton("24", callback_data="karat_24")],
        [InlineKeyboardButton("22", callback_data="karat_22")],
        [InlineKeyboardButton("21", callback_data="karat_21")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر عيار الذهب:", reply_markup=reply_markup)
    return KARAT

async def choose_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data["karat"] = int(query.data.split("_")[1])
    await query.edit_message_text(f"أرسل الكمية التي اشتريتها بالـ {user_data['unit']}:")
    return QUANTITY

async def get_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data["quantity"] = float(update.message.text)
    await update.message.reply_text(f"أرسل المبلغ الإجمالي الذي دفعته ({user_data['unit']}):")
    return TOTAL_COST

async def get_total_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_cost = float(update.message.text)
    user_data["total_cost"] = total_cost

    gold = get_gold_prices()
    karat = user_data["karat"]
    unit = user_data["unit"]
    quantity = user_data["quantity"]

    price_map = {24: gold["gram_24"], 22: gold["gram_22"], 21: gold["gram_21"]}
    current_price = price_map[karat]

    if unit == "mithqal":
        current_price *= 4.25  # تحويل المثقال إلى غرام تقريبي

    profit = (current_price - total_cost / quantity) * quantity
    color = "🟢" if profit > 0 else "🔴"
    await update.message.reply_text(f"{color} أرباحك: {profit:.2f} $")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# ------------------- إرسال الأسعار -------------------
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    msg = format_message()
    keyboard = [[InlineKeyboardButton("احتساب الأرباح", callback_data="start_profit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# ------------------- جدولة إرسال الأسعار -------------------
async def schedule_prices(app):
    for hour in range(10, 19):
        app.job_queue.run_daily(send_prices, time=time(hour, 0, 0), days=(0,1,2,3,4,5,6))

# ------------------- تشغيل البوت -------------------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_profit, pattern="start_profit")],
        states={
            UNIT: [CallbackQueryHandler(choose_unit, pattern="unit_.*")],
            KARAT: [CallbackQueryHandler(choose_karat, pattern="karat_.*")],
            QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_quantity)],
            TOTAL_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_total_cost)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)

    # إرسال الأسعار أول مرة عند تشغيل البوت
    await send_prices(app.bot)

    # جدولة الرسائل
    await schedule_prices(app)

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
