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
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @username أو -100xxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_TOTAL_PRICE = range(4)
user_buy_data = {}

# أيام الأسبوع بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- جلب أسعار الذهب ---
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
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- تنسيق الرسالة ---
def format_prices_message(prices, special_msg=""):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    if prices:
        for karat in ["24k","22k","21k"]:
            message += f"🔹 عيار {karat[:-1]}:\n"
            message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
            message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n"
        message += f"\n🔹 الأونصة: `{prices['ounce']:.2f}` $\n"
    if special_msg:
        message += f"\n{special_msg}"
    return message

# --- إرسال الأسعار التلقائية ---
async def send_prices_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    hour = now.hour
    prices = fetch_gold_prices()
    if not prices:
        return

    special_msg = ""
    if hour == 10:
        special_msg = "📈 تم فتح بورصة العراق"
    elif hour == 22:
        special_msg = "📉 تم إغلاق بورصة العراق"

    message = format_prices_message(prices, special_msg)
    await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

# --- زر حساب الأرباح ---
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
    keyboard = [[InlineKeyboardButton("غرام", callback_data="gram"), InlineKeyboardButton("مثقال", callback_data="mithqal")]]
    await query.edit_message_text("اختر الوحدة (غرام أو مثقال):", reply_markup=InlineKeyboardMarkup(keyboard))
    return BUY_UNIT

async def buy_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_buy_data[user_id]["unit"] = query.data
    await query.edit_message_text(f"أرسل العدد الذي اشتريته بالـ {query.data}:")
    return BUY_AMOUNT

async def buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        amount = float(update.message.text.replace(",","."))
        user_buy_data[user_id]["amount"] = amount
        await update.message.reply_text(f"أرسل السعر الإجمالي لشراء ({amount} {user_buy_data[user_id]['unit']}) بالدولار:")
        return BUY_TOTAL_PRICE
    except:
        await update.message.reply_text("⚠️ الرجاء إدخال رقم صالح للكمية.")
        return BUY_AMOUNT

async def buy_total_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",","."))
        data = user_buy_data[user_id]
        price_per_unit = total_price / data["amount"]
        data["price_per_unit"] = price_per_unit

        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        karat = data["karat"]
        unit = data["unit"]
        current_price = prices[karat][unit]
        profit = (current_price - price_per_unit) * data["amount"]
        color = "🟢" if profit >= 0 else "🔴"
        status = "ربح" if profit >=0 else "خسارة"

        await update.message.reply_text(
            f"{color} **نتيجة حساب أرباحك**\n"
            f"عيار الذهب: {karat}\n"
            f"الوحدة: {unit}\n"
            f"الكمية: {data['amount']}\n"
            f"سعر الشراء لكل وحدة: {price_per_unit:.2f} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{status}: {abs(profit):.2f} $",
            parse_mode=ParseMode.MARKDOWN
        )
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except:
        await update.message.reply_text("⚠️ الرجاء إدخال رقم صالح للسعر الإجمالي.")
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
        entry_points=[CallbackQueryHandler(buy_button, pattern="^buy$")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_amount)],
            BUY_TOTAL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_total_price)],
        },
        fallbacks=[MessageHandler(filters.Regex("^(إلغاء|/cancel)$"), cancel)]
    )
    app.add_handler(conv_handler)

    # إضافة المهمة المجدولة
    app.job_queue.run_repeating(send_prices_job, interval=3600, first=0)  # كل ساعة

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
