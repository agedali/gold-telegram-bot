import logging
import os
import requests
from datetime import datetime
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
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_TOTAL_PRICE = range(4)
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- جلب الأسعار ---
def fetch_gold_prices():
    """جلب الأسعار اللحظية من GoldAPI"""
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
    except Exception as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- تنسيق الرسائل ---
def format_prices_message(prices: dict, special_msg=""):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n"
    if special_msg:
        message += f"{special_msg}\n\n"
    for karat in ["24k","22k","21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n"
    message += f"🔹 الأونصة: `{prices['ounce']:.2f}` $\n\n"
    message += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message

# --- زر حساب الأرباح ---
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
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) الذي اشتريته بالدولار:")
    return BUY_TOTAL_PRICE

async def buy_total_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",", "."))
        data = user_buy_data[user_id]
        amount = float(update.message.text.replace(",", ".")) if False else 1  # سيتم إدخال الكمية بالرسالة
        # حساب سعر الوحدة
        unit_price = total_price / data.get("amount", 1)
        data["total_price"] = total_price
        data["unit_price"] = unit_price

        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        current_price = prices[data["karat"]][data["unit"]]
        profit = (current_price - unit_price) * data.get("amount", 1)

        color = "🟢 ربح" if profit >= 0 else "🔴 خسارة"
        await update.message.reply_text(
            f"💰 نتائج حساب أرباحك:\n"
            f"عيار الذهب: {data['karat']}\n"
            f"الوحدة: {data['unit']}\n"
            f"الكمية: {data.get('amount',1)}\n"
            f"السعر الإجمالي: {data['total_price']} $\n"
            f"سعر الوحدة: {data['unit_price']:.2f} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{color}: {profit:.2f} $"
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

# --- وظيفة إرسال الأسعار تلقائيًا ---
async def send_prices_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    hour = now.hour
    prices = fetch_gold_prices()
    if not prices:
        return
    special_msg = ""
    if hour == 10:
        special_msg = "📢 تم فتح بورصة العراق"
    elif hour == 22:
        special_msg = "📢 تم إغلاق بورصة العراق"
    message = format_prices_message(prices, special_msg)
    await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

# --- تشغيل البوت ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # حساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="^buy$")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_TOTAL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_total_price)],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel)],
    )
    app.add_handler(conv_handler)

    # إرسال الأسعار كل ساعة
    app.job_queue.run_repeating(send_prices_job, interval=3600, first=0)

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
