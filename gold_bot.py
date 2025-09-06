import logging
import os
import requests
from datetime import datetime, time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    JobQueue,
)

from bs4 import BeautifulSoup

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @channelusername أو -100xxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_TOTAL = range(3)
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- جلب أسعار الذهب ---
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }
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
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- جلب أسعار الدولار واليورو مقابل الدينار العراقي ---
def fetch_currency_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        res = requests.get(url)
        soup = BeautifulSoup(res.content, "html.parser")
        table = soup.find("table")
        rates = {}
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            name = cols[0].text.strip()
            buy = cols[1].text.strip()
            sell = cols[2].text.strip()
            rates[name] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        logging.error(f"❌ Error fetching currency rates: {e}")
        return None

# --- تنسيق رسالة الأسعار ---
def format_prices_message(prices, currency_rates=None, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب والدولار اليوم - {day} {date_str}** 💰\n\n"
    if special_msg:
        message += f"⚡ {special_msg} ⚡\n\n"
    for karat in ["24k","22k","21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n"
    message += f"🔹 الأونصة: `{prices['ounce']:.2f}` $\n\n"

    if currency_rates:
        message += "💵 **أسعار العملات مقابل الدينار العراقي** 💵\n"
        for name, rate in currency_rates.items():
            message += f"{name}: شراء `{rate['buy']}` | بيع `{rate['sell']}`\n"
    return message

# --- إرسال الأسعار ---
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    currency_rates = fetch_currency_rates()
    if prices:
        msg = format_prices_message(prices, currency_rates)
        await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

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
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) الذي قمت بشرائه بالدولار:")
    return BUY_TOTAL

async def buy_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    data = user_buy_data[user_id]
    try:
        total = float(update.message.text.replace(",","."))  
        amount = 1  # سيحسب تلقائي لاحقًا حسب الوحدة
        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        unit = data["unit"]
        karat = data["karat"]
        # حساب السعر لكل وحدة
        if unit == "gram":
            unit_price = total / 1  # المستخدم كتب السعر الإجمالي لغرام واحد
        else:
            unit_price = total / 5  # المثقال = 5 غرام
        current_price = prices[karat][unit]
        profit = (current_price - unit_price) * 1  # كمية = 1 وحدة

        color = "🟢" if profit >= 0 else "🔴"
        status = "ربح" if profit >= 0 else "خسارة"

        await update.message.reply_text(
            f"{color} **نتائج حساب أرباحك:**\n"
            f"عيار الذهب: {karat}\n"
            f"الوحدة: {unit}\n"
            f"السعر الذي اشتريت به لكل وحدة: {unit_price:.2f} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"الحالة: {status} {profit:.2f} $",
            parse_mode="Markdown"
        )
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح.")
        return BUY_TOTAL

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_buy_data.pop(user_id, None)
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# --- Main ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # إضافة محادثة حساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_total)],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel)],
    )
    app.add_handler(conv_handler)

    # زر حساب الأرباح
    async def send_buy_button(context: ContextTypes.DEFAULT_TYPE):
        keyboard = [[InlineKeyboardButton("حساب أرباحك 💰", callback_data="buy")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=CHAT_ID, text="اضغط لحساب أرباحك:", reply_markup=reply_markup)

    # إرسال الأسعار أول مرة عند التشغيل
    async def first_send():
        await send_prices(ContextTypes.DEFAULT_TYPE(application=app, job=None))
        await send_buy_button(ContextTypes.DEFAULT_TYPE(application=app, job=None))

    import asyncio
    asyncio.run(first_send())

    # جدولة كل ساعة من 10 صباحًا حتى 6 مساءً
    for hour in range(10, 19):
        app.job_queue.run_daily(send_prices, time(hour, 0), days=(0,1,2,3,4,5,6))

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
