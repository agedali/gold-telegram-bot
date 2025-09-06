import logging
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @channelusername أو -100xxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_PRICE = range(4)
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- جلب أسعار الذهب ---
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
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
        logging.error(f"Error fetching gold prices: {e}")
        return None

# --- جلب أسعار الدولار واليورو مقابل الدينار ---
def fetch_currency_rates():
    url = "https://qamaralfajr.com/production/exchange_rates.php"
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        rates = {}
        rows = soup.find_all("tr")[1:]
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                currency = cols[0].get_text(strip=True)
                buy = cols[1].get_text(strip=True)
                sell = cols[2].get_text(strip=True)
                if currency in ["USD", "EUR"]:
                    rates[currency] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        logging.error(f"Error fetching currency rates: {e}")
        return None

# --- تنسيق رسالة الأسعار ---
def format_prices_message(special_msg=""):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار اليوم - {day} {date_str}** 💰\n\n"

    gold = fetch_gold_prices()
    if gold:
        for karat in ["24k","22k","21k"]:
            message += f"🔹 عيار {karat[:-1]}:\n"
            message += f"   - الغرام: `{gold[karat]['gram']:.2f}` $\n"
            message += f"   - المثقال: `{gold[karat]['mithqal']:.2f}` $\n"
        message += f"🔹 الأونصة: `{gold['ounce']:.2f}` $\n\n"
    else:
        message += "⚠️ لم نتمكن من جلب أسعار الذهب.\n\n"

    currency = fetch_currency_rates()
    if currency:
        for cur in currency:
            message += f"💵 {cur}:\n"
            message += f"   - شراء: `{currency[cur]['buy']}` IQD\n"
            message += f"   - بيع: `{currency[cur]['sell']}` IQD\n"
    else:
        message += "⚠️ لم نتمكن من جلب أسعار العملات.\n"

    if special_msg:
        message = f"**{special_msg}**\n\n" + message

    return message

# --- ارسال الأسعار للقناة ---
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    message = format_prices_message()
    await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

# --- حساب الأرباح ---
async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("24k", callback_data="24k"),
         InlineKeyboardButton("22k", callback_data="22k"),
         InlineKeyboardButton("21k", callback_data="21k")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر عيار الذهب الذي اشتريته:", reply_markup=reply_markup)
    return BUY_KARAT

async def buy_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id] = {"karat": query.data}
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="gram"),
         InlineKeyboardButton("مثقال", callback_data="mithqal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر الوحدة (غرام أو مثقال):", reply_markup=reply_markup)
    return BUY_UNIT

async def buy_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id]["unit"] = query.data
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) الذي تم شراؤه بالدولار:")
    return BUY_AMOUNT

async def buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",","."))
        user_buy_data[user_id]["total_price"] = total_price
        await update.message.reply_text("✅ تم استلام السعر الإجمالي، جاري حساب الربح/الخسارة...")
        # حساب سعر الوحدة
        data = user_buy_data[user_id]
        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        unit = data["unit"]
        karat = data["karat"]
        amount = 1  # نحسب السعر لكل وحدة واحدة
        unit_price = data["total_price"] / 1  # المستخدم ادخل السعر الإجمالي لكل الوحدة

        current_price = prices[karat][unit]
        profit = current_price - unit_price

        # ألوان الربح والخسارة
        if profit >= 0:
            result_text = f"💵 أرباح: {profit:.2f} $"
        else:
            result_text = f"❌ خسارة: {profit:.2f} $"

        await update.message.reply_text(
            f"💰 نتائج حساب أرباحك:\n"
            f"عيار الذهب: {karat}\n"
            f"الوحدة: {unit}\n"
            f"السعر الإجمالي المدخل: {data['total_price']} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{result_text}"
        )
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح.")
        return BUY_AMOUNT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_buy_data.pop(user_id, None)
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# --- Main ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # حساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار كل دقيقة
    from telegram.ext import JobQueue
    job_queue = app.job_queue
    job_queue.run_repeating(send_prices, interval=60, first=0)  # كل 60 ثانية

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
