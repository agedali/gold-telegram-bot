import logging
import os
import requests
from datetime import datetime, time
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    CommandHandler,
)

# ---------- إعداد اللوج ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------- مفاتيح البيئة ----------
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# ---------- مراحل حساب الأرباح ----------
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_PRICE = range(4)
user_buy_data = {}

# ---------- خريطة الأيام بالعربي ----------
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# ---------- جلب أسعار الذهب ----------
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        return {
            "24k": {"gram": data.get("price_gram_24k"), "mithqal": data.get("price_gram_24k")*5, "ounce": data.get("price_ounce")},
            "22k": {"gram": data.get("price_gram_22k"), "mithqal": data.get("price_gram_22k")*5, "ounce": data.get("price_ounce") * (22/24)},
            "21k": {"gram": data.get("price_gram_21k"), "mithqal": data.get("price_gram_21k")*5, "ounce": data.get("price_ounce") * (21/24)},
        }
    except Exception as e:
        logging.error("❌ Error fetching gold prices: %s", e)
        return None

# ---------- جلب سعر الدولار واليورو مقابل الدينار العراقي ----------
def fetch_currency_rates():
    url = "https://qamaralfajr.com/production/exchange_rates.php"
    try:
        r = requests.get(url)
        soup = BeautifulSoup(r.content, "html.parser")
        rows = soup.find_all("tr")
        rates = {}
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                currency = cols[0].text.strip()
                buy = cols[1].text.strip()
                sell = cols[2].text.strip()
                if currency in ["USD", "EUR"]:
                    rates[currency] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        logging.error("❌ Error fetching currency rates: %s", e)
        return None

# ---------- تنسيق الرسائل ----------
def format_prices_message(special_msg=""):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")

    gold_prices = fetch_gold_prices()
    currency_rates = fetch_currency_rates()
    if not gold_prices or not currency_rates:
        return "⚠️ تعذر جلب البيانات حاليًا."

    usd_buy = float(currency_rates["USD"]["buy"])
    usd_sell = float(currency_rates["USD"]["sell"])
    eur_buy = float(currency_rates["EUR"]["buy"])
    eur_sell = float(currency_rates["EUR"]["sell"])

    message = f"💰 **أسعار الذهب والعملات - {day} {date_str}** 💰\n\n"

    for karat in ["24k","22k","21k"]:
        g = gold_prices[karat]["gram"]
        m = gold_prices[karat]["mithqal"]
        o = gold_prices[karat]["ounce"]
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{g:.2f}` $ | `{g*usd_sell:.0f}` د.ع\n"
        message += f"   - المثقال: `{m:.2f}` $ | `{m*usd_sell:.0f}` د.ع\n"
        message += f"   - الأونصة: `{o:.2f}` $ | `{o*usd_sell:.0f}` د.ع\n\n"

    message += f"💵 الدولار: شراء `{usd_buy}` د.ع | بيع `{usd_sell}` د.ع\n"
    message += f"💶 اليورو: شراء `{eur_buy}` د.ع | بيع `{eur_sell}` د.ع\n\n"
    if special_msg:
        message = f"**{special_msg}**\n\n" + message

    message += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message

# ---------- حساب الأرباح ----------
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
        amount = float(update.message.text.replace(",","."))
        user_buy_data[user_id]["amount"] = amount
        await update.message.reply_text("تم استلام السعر الإجمالي.")
        # حساب الربح مباشرة
        data = user_buy_data[user_id]
        karat = data["karat"]
        unit = data["unit"]
        total_price = data["amount"]
        gold_prices = fetch_gold_prices()
        currency_rates = fetch_currency_rates()
        if not gold_prices or not currency_rates:
            await update.message.reply_text("⚠️ تعذر جلب البيانات حالياً.")
            return ConversationHandler.END

        current_price_usd = gold_prices[karat][unit]
        unit_count = total_price / current_price_usd
        profit = (current_price_usd - (total_price/unit_count)) * unit_count

        if profit >=0:
            msg_profit = f"💰 ربح: {profit:.2f} $"
        else:
            msg_profit = f"❌ خسارة: {abs(profit):.2f} $"

        await update.message.reply_text(f"نتائج حساب أرباحك:\n"
                                        f"عيار الذهب: {karat}\n"
                                        f"الوحدة: {unit}\n"
                                        f"السعر الإجمالي: {total_price} $\n"
                                        f"{msg_profit}")
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إدخال رقم صالح.")
        return BUY_AMOUNT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_buy_data.pop(user_id, None)
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# ---------- إرسال الأسعار تلقائي ----------
async def send_prices(context: ContextTypes.DEFAULT_TYPE, special_msg=""):
    msg = format_prices_message(special_msg)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

# ---------- الجدول الزمني ----------
def schedule_prices(app):
    for hour in range(10, 19):  # من 10 صباحا حتى 6 مساء
        app.job_queue.run_daily(send_prices, time(hour, 0, 0), data=None)

# ---------- بدء البوت ----------
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

    # إرسال أول رسالة عند التشغيل
    import asyncio
    asyncio.run(send_prices(ContextTypes.DEFAULT_TYPE(app)))

    # جدولة الرسائل
    schedule_prices(app)

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
