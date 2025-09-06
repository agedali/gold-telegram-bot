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
)

# ----------------- إعداد اللوج -----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ----------------- مفاتيح البيئة -----------------
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# ----------------- مراحل حساب الأرباح -----------------
BUY_KARAT, BUY_UNIT, BUY_AMOUNT = range(3)
user_buy_data = {}

# ----------------- خريطة الأيام بالعربي -----------------
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# ----------------- جلب أسعار الذهب بالدولار -----------------
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return {
            "24k": {"gram": data.get("price_gram_24k"), "mithqal": data.get("price_gram_24k")*5},
            "22k": {"gram": data.get("price_gram_22k"), "mithqal": data.get("price_gram_22k")*5},
            "21k": {"gram": data.get("price_gram_21k"), "mithqal": data.get("price_gram_21k")*5},
            "ounce": data.get("price_ounce")
        }
    except Exception as e:
        logging.error(f"❌ خطأ في جلب أسعار الذهب: {e}")
        return None

# ----------------- جلب أسعار الدولار واليورو مقابل الدينار -----------------
from bs4 import BeautifulSoup

def fetch_currency_rates():
    url = "https://qamaralfajr.com/production/exchange_rates.php"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.find_all("tr")
        usd_buy = usd_sell = eur_buy = eur_sell = None
        for row in rows:
            cols = row.find_all("td")
            if not cols:
                continue
            name = cols[0].text.strip()
            if "دولار" in name:
                usd_buy, usd_sell = cols[1].text.strip(), cols[2].text.strip()
            elif "يورو" in name:
                eur_buy, eur_sell = cols[1].text.strip(), cols[2].text.strip()
        return {
            "USD": {"buy": float(usd_buy.replace(",","")), "sell": float(usd_sell.replace(",",""))},
            "EUR": {"buy": float(eur_buy.replace(",","")), "sell": float(eur_sell.replace(",",""))},
        }
    except Exception as e:
        logging.error(f"❌ خطأ في جلب أسعار العملات: {e}")
        return None

# ----------------- تنسيق الرسائل -----------------
def format_prices_message(prices, currencies, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n"
    if special_msg:
        message += f"\n{special_msg}\n"
    for karat in ["24k","22k","21k"]:
        message += f"\n🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام بالدولار: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال بالدولار: `{prices[karat]['mithqal']:.2f}` $\n"
        if currencies:
            usd_rate = currencies['USD']['sell']
            message += f"   - الغرام بالدينار: `{prices[karat]['gram']*usd_rate:.0f}` IQD\n"
            message += f"   - المثقال بالدينار: `{prices[karat]['mithqal']*usd_rate:.0f}` IQD\n"
    message += f"\n🔹 الأونصة بالدولار: `{prices['ounce']:.2f}` $\n"
    if currencies:
        message += f"🔹 الأونصة بالدينار: `{prices['ounce']*currencies['USD']['sell']:.0f}` IQD\n"
        message += "\n💵 أسعار العملات مقابل الدينار العراقي:\n"
        message += f"   - الدولار USD: شراء {currencies['USD']['buy']} - بيع {currencies['USD']['sell']}\n"
        message += f"   - اليورو EUR: شراء {currencies['EUR']['buy']} - بيع {currencies['EUR']['sell']}\n"
    message += "\n💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message

# ----------------- حساب الأرباح -----------------
async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[
        InlineKeyboardButton("24k", callback_data="24k"),
        InlineKeyboardButton("22k", callback_data="22k"),
        InlineKeyboardButton("21k", callback_data="21k")
    ]]
    await query.edit_message_text("اختر عيار الذهب الذي اشتريته:", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_KARAT

async def buy_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id] = {"karat": query.data}
    keyboard = [[
        InlineKeyboardButton("غرام", callback_data="gram"),
        InlineKeyboardButton("مثقال", callback_data="mithqal")
    ]]
    await query.edit_message_text("اختر الوحدة (غرام أو مثقال):", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_UNIT

async def buy_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id]["unit"] = query.data
    await query.edit_message_text(f"أرسل السعر الإجمالي للشراء ({query.data}) بالدولار:")
    return BUY_AMOUNT

async def buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",","."))  # السعر الإجمالي
        data = user_buy_data[user_id]
        amount = 1  # نفترض 1 وحدة افتراضي
        if data["unit"] == "gram":
            amount = float(update.message.text)  # هنا يمكن تعديل إذا تريد السماح للمستخدم بإدخال عدد الغرامات
        # حساب سعر الوحدة
        unit_price = total_price / amount
        data["amount"] = amount
        data["unit_price"] = unit_price
        # جلب الأسعار الحالية
        prices = fetch_gold_prices()
        currencies = fetch_currency_rates()
        current_price_usd = prices[data["karat"]][data["unit"]]
        profit = (current_price_usd - unit_price) * amount
        color = "🟢 ربح" if profit>=0 else "🔴 خسارة"
        msg = f"💰 نتائج حساب أرباحك:\n"
        msg += f"عيار الذهب: {data['karat']}\nالوحدة: {data['unit']}\n"
        msg += f"سعر الشراء لكل وحدة: {unit_price:.2f} $\n"
        msg += f"السعر الحالي: {current_price_usd:.2f} $\n"
        msg += f"{color}: {profit:.2f} $\n"
        if currencies:
            msg += f"السعر الحالي بالدينار: {current_price_usd*currencies['USD']['sell']:.0f} IQD"
        await update.message.reply_text(msg)
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

# ----------------- إرسال الأسعار تلقائيًا -----------------
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    currencies = fetch_currency_rates()
    if not prices:
        return
    now = datetime.now()
    special_msg = None
    if now.hour == 10:
        special_msg = "📢 تم فتح بورصة العراق"
    elif now.hour == 22:
        special_msg = "📢 تم إغلاق بورصة العراق"
    message = format_prices_message(prices, currencies, special_msg)
    await context.bot.send_message(chat_id=CHAT_ID, text=message)

# ----------------- إعداد البوت -----------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_amount)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel)],
    )
    app.add_handler(conv_handler)

    # إضافة جدولة إرسال الأسعار كل ساعة من 10 صباحًا حتى 10 مساءً
    for hour in range(10, 23):
        app.job_queue.run_daily(send_prices, time(hour, 0, 0))

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
