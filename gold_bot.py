import os
import logging
import asyncio
import requests
from datetime import datetime
from bs4 import BeautifulSoup
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
BOT_CHAT_ID = os.getenv("BOT_CHAT_ID")       # معرف البوت نفسه (يمكن استخدام رقمك الشخصي لاختبار)
CHANNEL_ID = os.getenv("TELEGRAM_CHAT_ID")   # معرف القناة
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_TOTAL = range(4)

# تخزين بيانات المستخدم أثناء الحساب
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# ---------------- جلب الأسعار ----------------

def fetch_gold_prices():
    """جلب أسعار الذهب من GOLDAPI"""
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "24k": {"gram": data.get("price_gram_24k"), "mithqal": data.get("price_gram_24k")*5, "ounce": data.get("price_ounce")},
            "22k": {"gram": data.get("price_gram_22k"), "mithqal": data.get("price_gram_22k")*5, "ounce": None},
            "21k": {"gram": data.get("price_gram_21k"), "mithqal": data.get("price_gram_21k")*5, "ounce": None},
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

def fetch_currency_rates():
    """سحب سعر الدولار واليورو مقابل الدينار العراقي من الموقع"""
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        rates = {}
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            currency = cols[0].text.strip()
            buy = cols[1].text.strip()
            sell = cols[2].text.strip()
            rates[currency] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        logging.error(f"❌ Error fetching currency rates: {e}")
        return {}

# ---------------- تنسيق الرسائل ----------------

def format_prices_message(prices, currency_rates, special_msg=""):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    for karat in ["24k","22k","21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n"
        if prices[karat]["ounce"]:
            message += f"   - الأونصة: `{prices[karat]['ounce']:.2f}` $\n"
        message += "\n"
    
    if currency_rates:
        message += "💱 **أسعار الصرف مقابل الدينار العراقي:**\n"
        for cur in ["USD", "EUR"]:
            if cur in currency_rates:
                message += f"{cur} - شراء: `{currency_rates[cur]['buy']}`  بيع: `{currency_rates[cur]['sell']}`\n"
    
    if special_msg:
        message += f"\n💡 {special_msg}"
    return message

# ---------------- حساب الأرباح ----------------

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
        user_buy_data[user_id]["total"] = total_price
        await update.message.reply_text("العملية مسجلة! سيتم حساب الأرباح تلقائيًا عند جلب الأسعار.")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح للسعر الإجمالي.")
        return BUY_AMOUNT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_buy_data.pop(user_id, None)
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# ---------------- إرسال الرسائل ----------------

async def send_prices(app):
    prices = fetch_gold_prices()
    currency_rates = fetch_currency_rates()
    if not prices:
        logging.error("❌ Error fetching gold prices")
        return
    msg = format_prices_message(prices, currency_rates)
    
    # إرسال الرسالة أولًا للبوت نفسه
    message = await app.bot.send_message(chat_id=BOT_CHAT_ID, text=msg, parse_mode="Markdown")
    
    # إعادة إرسالها للقناة
    await app.bot.forward_message(chat_id=CHANNEL_ID, from_chat_id=BOT_CHAT_ID, message_id=message.message_id)
    
    # حساب الأرباح لكل مستخدم
    for user_id, data in user_buy_data.items():
        karat = data["karat"]
        unit = data["unit"]
        total_price = data["total"]
        unit_price = total_price / 1  # في المستقبل يمكن تعديل حسب الكمية
        current_price = prices[karat][unit]
        profit = (current_price - unit_price) * 1
        text = f"💰 نتائج حساب أرباحك:\n"
        text += f"عيار الذهب: {karat}\n"
        text += f"الوحدة: {unit}\n"
        text += f"السعر الإجمالي: {total_price} $\n"
        text += f"السعر الحالي: {current_price:.2f} $\n"
        if profit >=0:
            text += f"الربح: {profit:.2f} $ ✅"
        else:
            text += f"الخسارة: {profit:.2f} $ ❌"
        await app.bot.send_message(chat_id=user_id, text=text)

async def scheduled_prices(app):
    """إرسال الأسعار كل ساعة من 10 صباحًا حتى 6 مساءً"""
    while True:
        now = datetime.now()
        if 10 <= now.hour <= 18:
            await send_prices(app)
        await asyncio.sleep(3600)  # كل ساعة

# ---------------- التشغيل ----------------

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # حساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("buy", buy_button)],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat)],
            BUY_UNIT: [CallbackQueryHandler(buy_unit)],
            BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)
    
    # تشغيل البوت
    asyncio.create_task(scheduled_prices(app))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
