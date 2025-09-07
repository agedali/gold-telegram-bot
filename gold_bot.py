import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ConversationHandler, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import asyncio
import nest_asyncio

nest_asyncio.apply()

# --- متغيرات البيئة ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# --- مراحل إدخال البيانات ---
UNIT, GOLD_TYPE, QUANTITY, TOTAL_COST = range(4)
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
            "24": data["price_gram_24k"],
            "22": data["price_gram_22k"],
            "21": data["price_gram_21k"],
            "ounce": data["price"]
        }
    except Exception as e:
        print("❌ خطأ في استدعاء أسعار الذهب:", e)
        return None

# --- سحب أسعار الصرف ---
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

# --- صياغة الرسالة الرئيسية ---
def format_message():
    gold = get_gold_prices()
    fx = get_fx_rates()

    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    if not gold:
        msg += "❌ خطأ في جلب أسعار الذهب.\n"
    else:
        msg += "💰 أسعار الذهب بالدولار:\n"
        msg += f"• عيار 24: {gold['24']:.2f} $\n"
        msg += f"• عيار 22: {gold['22']:.2f} $\n"
        msg += f"• عيار 21: {gold['21']:.2f} $\n"
        msg += f"• الأونصة: {gold['ounce']:.2f} $\n"
        if fx:
            msg += f"\n💰 تقريبًا بالدينار العراقي (سعر البيع):\n"
            msg += f"• عيار 24: {(gold['24']*float(fx['USD']['sell'])):.0f} د.ع\n"
            msg += f"• عيار 22: {(gold['22']*float(fx['USD']['sell'])):.0f} د.ع\n"
            msg += f"• عيار 21: {(gold['21']*float(fx['USD']['sell'])):.0f} د.ع\n"
    if not fx:
        msg += "\n❌ خطأ في جلب أسعار الصرف."
    else:
        msg += "\n💱 أسعار العملات مقابل الدينار العراقي:\n"
        for curr in fx:
            msg += f"• {curr} شراء: {fx[curr]['buy']} | بيع: {fx[curr]['sell']}\n"
    return msg

# --- handlers للأرباح ---
async def profit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="unit_gram"), InlineKeyboardButton("مثقال", callback_data="unit_mithqal")]
    ]
    await update.callback_query.message.reply_text("اختر الوحدة:", reply_markup=InlineKeyboardMarkup(keyboard))
    return UNIT

async def unit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data['unit'] = query.data.split("_")[1]  # gram أو mithqal
    keyboard = [
        [InlineKeyboardButton("24", callback_data="gold_24")],
        [InlineKeyboardButton("22", callback_data="gold_22")],
        [InlineKeyboardButton("21", callback_data="gold_21")]
    ]
    await query.message.reply_text("اختر عيار الذهب:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GOLD_TYPE

async def gold_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data['gold_type'] = query.data.split("_")[1]  # 24, 22, 21
    await query.message.reply_text(f"ادخل الكمية ({user_data['unit']}):")
    return QUANTITY

async def quantity_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data['quantity'] = float(update.message.text)
    await update.message.reply_text(f"ادخل المبلغ الإجمالي للشراء ({user_data['unit']}):")
    return TOTAL_COST

async def total_cost_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_cost = float(update.message.text)
    quantity = user_data['quantity']
    gold_type = user_data['gold_type']
    unit = user_data['unit']

    gold_prices = get_gold_prices()
    if not gold_prices:
        await update.message.reply_text("❌ خطأ في جلب أسعار الذهب.")
        return ConversationHandler.END

    current_price = gold_prices[gold_type]  # بالدولار
    # تحويل المثقال إلى غرام إذا لزم الأمر
    if unit == "mithqal":
        quantity_in_grams = quantity * 4.25  # 1 مثقال ≈ 4.25 غرام
    else:
        quantity_in_grams = quantity

    profit = (current_price - (total_cost / quantity_in_grams)) * quantity_in_grams
    color = "🟢" if profit > 0 else "🔴"
    await update.message.reply_text(f"{color} أرباحك: {profit:.2f} $")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- زر callback handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "profit":
        await profit_start(update, context)
        return UNIT

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
        entry_points=[CallbackQueryHandler(button_handler, pattern="^profit$")],
        states={
            UNIT: [CallbackQueryHandler(unit_choice, pattern="^unit_")],
            GOLD_TYPE: [CallbackQueryHandler(gold_choice, pattern="^gold_")],
            QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_input)],
            TOTAL_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, total_cost_input)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(conv_handler)

    # إرسال الأسعار عند التشغيل
    await send_initial_prices(app)

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
