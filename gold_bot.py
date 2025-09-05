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

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @channelusername أو -100xxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_TOTAL_PRICE = range(4)

# تخزين بيانات المستخدم أثناء الحساب
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

def fetch_gold_prices():
    """جلب الأسعار اللحظية من GoldAPI"""
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
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

def format_prices_message(prices: dict, special_msg=None):
    """تنسيق رسالة الأسعار مع التاريخ واليوم"""
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    message += f"🔹 أونصة الذهب: `{prices['ounce']:.2f}` $\n\n"
    for karat in ["24k","22k","21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    if special_msg:
        message += f"📌 {special_msg}\n\n"
    message += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message

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
    await query.edit_message_text(f"أرسل عدد {query.data} التي اشتريتها:")
    return BUY_AMOUNT

async def buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        amount = float(update.message.text.replace(",","."))  # يدعم النقطة والفاصلة
        user_buy_data[user_id]["amount"] = amount
        unit = user_buy_data[user_id]["unit"]
        await update.message.reply_text(f"أرسل السعر الإجمالي لشراء ({amount} {unit}) بالدولار:")
        return BUY_TOTAL_PRICE
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح للكمية.")
        return BUY_AMOUNT

async def buy_total_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",","."))  # يدعم النقطة والفاصلة
        data = user_buy_data[user_id]
        amount = data["amount"]
        price_per_unit = total_price / amount
        data["price_per_unit"] = price_per_unit

        # جلب الأسعار الحالية
        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        karat = data["karat"]
        unit = data["unit"]
        current_price = prices[karat][unit]
        profit = (current_price - price_per_unit) * amount
        if profit >= 0:
            profit_text = f"🟢 ربح: {profit:.2f} $"
        else:
            profit_text = f"🔴 خسارة: {profit:.2f} $"

        # إرسال رسالة النتائج مع الأسعار الحالية
        message = f"💰 نتائج حساب أرباحك:\n" \
                  f"عيار الذهب: {karat}\n" \
                  f"الوحدة: {unit}\n" \
                  f"الكمية: {amount}\n" \
                  f"سعر الوحدة: {price_per_unit:.2f} $\n" \
                  f"السعر الحالي: {current_price:.2f} $\n" \
                  f"{profit_text}\n\n" \
                  f"{format_prices_message(prices)}"
        await update.message.reply_text(message)
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

# --- الإرسال التلقائي كل 3 ساعات ---
async def send_prices_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    prices = fetch_gold_prices()
    if not prices:
        logging.error("⚠️ تعذر جلب أسعار الذهب لإرسالها تلقائيًا")
        return

    if time(10, 0) <= now.time() <= time(17, 0):
        if now.hour == 10:
            special_msg = "📈 تم فتح بورصة العراق"
        elif now.hour == 17:
            special_msg = "📉 تم إغلاق بورصة العراق"
        else:
            special_msg = None
        message = format_prices_message(prices, special_msg=special_msg)
        await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

# -------------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # زر حساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_amount)],
            BUY_TOTAL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_total_price)],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel)],
    )
    app.add_handler(conv_handler)

    # جدولة إرسال الأسعار كل 3 ساعات
    app.job_queue.run_repeating(send_prices_job, interval=10800, first=0)

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
