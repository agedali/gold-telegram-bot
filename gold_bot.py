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
    CommandHandler,
    filters,
)
import asyncio

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @channelusername أو -100xxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_PRICE = range(3)

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
            "ounce": data.get("price_ounce"),
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

def format_prices_message(prices: dict, special_msg=""):
    """تنسيق رسالة الأسعار مع التاريخ"""
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    for karat in ["24k","22k","21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    if prices.get("ounce"):
        message += f"🔹 الأونصة: `{prices['ounce']:.2f}` $\n\n"
    if special_msg:
        message += f"{special_msg}\n"
    message += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message

async def send_prices_job(context: ContextTypes.DEFAULT_TYPE):
    """إرسال الأسعار التلقائي"""
    prices = fetch_gold_prices()
    if not prices:
        logging.error("⚠️ تعذر جلب أسعار الذهب حالياً.")
        return
    hour = datetime.now().hour
    special_msg = ""
    if hour == 10:
        special_msg = "📈 تم فتح بورصة العراق"
    elif hour == 22:
        special_msg = "📉 تم إغلاق بورصة العراق"
    message = format_prices_message(prices, special_msg)
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
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) الذي قمت بشراءه بالدولار:")
    return BUY_PRICE

async def buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",","."))
        data = user_buy_data[user_id]
        amount = data.get("amount", 1)
        unit_price = total_price / amount
        data["total_price"] = total_price
        data["unit_price"] = unit_price

        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        karat = data["karat"]
        unit = data["unit"]
        current_price = prices[karat][unit]
        profit = (current_price - unit_price) * amount

        result_msg = f"💰 **نتائج حساب أرباحك** 💰\n\n" \
                     f"عيار الذهب: {karat}\n" \
                     f"الوحدة: {unit}\n" \
                     f"السعر الإجمالي: {total_price} $\n" \
                     f"السعر لكل وحدة: {unit_price:.2f} $\n" \
                     f"السعر الحالي: {current_price:.2f} $\n"

        if profit >= 0:
            result_msg += f"✅ **أرباح:** {profit:.2f} $"
        else:
            result_msg += f"❌ **خسارة:** {profit:.2f} $"

        await update.message.reply_text(result_msg, parse_mode="Markdown")
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح للسعر الإجمالي.")
        return BUY_PRICE

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
            BUY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار فورًا لتجربة
    app.job_queue.run_once(send_prices_job, when=0)

    # جدولة الأسعار كل ساعة من 10 صباحًا حتى 10 مساءً
    for hour in range(10, 23):
        app.job_queue.run_daily(send_prices_job, time=time(hour,0,0))

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
