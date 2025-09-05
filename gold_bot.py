import logging
import os
import requests
from datetime import datetime, time, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
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
GOLDPRICEZ_KEY = os.getenv("GOLDPRICEZ_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_TOTAL_PRICE = range(4)
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

def fetch_gold_prices():
    """جلب أسعار الذهب من Goldpricez.com"""
    url = f"https://goldpricez.com/api/rates/currency/usd/measure/all"
    headers = {"X-API-KEY": GOLDPRICEZ_KEY}
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return {
            "24k": {"gram": data.get("gram_in_usd"), "mithqal": data.get("gram_in_usd")*5},
            "22k": {"gram": round(data.get("gram_in_usd")*0.916,2), "mithqal": round(data.get("gram_in_usd")*0.916*5,2)},
            "21k": {"gram": round(data.get("gram_in_usd")*0.875,2), "mithqal": round(data.get("gram_in_usd")*0.875*5,2)},
            "ounce": data.get("ounce_price_usd")
        }
    except Exception as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

def format_prices_message(prices, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    if special_msg:
        message += f"{special_msg}\n\n"
    message += f"🔹 الأونصة: `{prices['ounce']:.2f}` $\n\n"
    for karat in ["24k", "22k", "21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    message += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message

async def send_prices_job(app: ApplicationBuilder):
    """إرسال الأسعار تلقائياً كل ساعة بين 10 صباحًا و10 مساءً"""
    prices = fetch_gold_prices()
    if not prices:
        return
    now = datetime.now()
    if now.hour == 10:
        special_msg = "🟢 تم فتح بورصة العراق"
    elif now.hour == 22:
        special_msg = "🔴 تم إغلاق بورصة العراق"
    else:
        special_msg = None
    message = format_prices_message(prices, special_msg)
    await app.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

# --- حساب الأرباح ---
async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("24k", callback_data="24k"),
         InlineKeyboardButton("22k", callback_data="22k"),
         InlineKeyboardButton("21k", callback_data="21k")]
    ]
    await query.edit_message_text("اختر عيار الذهب الذي اشتريته:", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_KARAT

async def buy_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id] = {"karat": query.data}
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="gram"),
         InlineKeyboardButton("مثقال", callback_data="mithqal")]
    ]
    await query.edit_message_text("اختر الوحدة (غرام أو مثقال):", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_UNIT

async def buy_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id]["unit"] = query.data
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) بالدولار:")
    return BUY_TOTAL_PRICE

async def buy_total_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",", "."))
        data = user_buy_data[user_id]
        amount = 1  # يمكن تعديل لاحقاً إذا أردنا إدخال عدد الغرامات/المثقال
        price_per_unit = total_price / amount
        data["total"] = total_price
        data["price_per_unit"] = price_per_unit

        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        karat = data["karat"]
        unit = data["unit"]
        current_price = prices[karat][unit]
        profit = (current_price - price_per_unit) * amount

        if profit >= 0:
            profit_msg = f"✅ ربح: {profit:.2f} $"
        else:
            profit_msg = f"❌ خسارة: {profit:.2f} $"

        await update.message.reply_text(
            f"💰 نتائج حساب أرباحك:\n"
            f"عيار الذهب: {karat}\n"
            f"الوحدة: {unit}\n"
            f"السعر الإجمالي: {total_price} $\n"
            f"سعر الوحدة: {price_per_unit:.2f} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{profit_msg}"
        )
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح للسعر الإجمالي.")
        return BUY_TOTAL_PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_buy_data.pop(user_id, None)
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# -------------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # زر حساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_TOTAL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_total_price)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel)],
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار كل ساعة
    for hour in range(10, 23):
        app.job_queue.run_daily(send_prices_job, time=time(hour, 0, 0), context=app)

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
