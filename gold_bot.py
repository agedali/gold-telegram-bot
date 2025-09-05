import logging
import os
import requests
from datetime import datetime
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
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_PRICE = range(4)

# تخزين بيانات المستخدم أثناء الحساب
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- دالة جلب الأسعار ---
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # التأكد من عدم وجود None
        gram_24k = data.get("price_gram_24k") or 0.0
        gram_22k = data.get("price_gram_22k") or 0.0
        gram_21k = data.get("price_gram_21k") or 0.0
        ounce = data.get("price_ounce") or 0.0

        return {
            "24k": {"gram": gram_24k, "mithqal": gram_24k*5},
            "22k": {"gram": gram_22k, "mithqal": gram_22k*5},
            "21k": {"gram": gram_21k, "mithqal": gram_21k*5},
            "ounce": ounce
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- رسالة الأسعار ---
def format_prices_message(prices, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")

    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    for karat in ["24k","22k","21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    ounce_price = prices.get("ounce")
    if ounce_price == 0.0:
        ounce_text = "غير متوفر"
    else:
        ounce_text = f"{ounce_price:.2f} $"
    message += f"🔹 الأونصة: `{ounce_text}`\n\n"

    if special_msg:
        message += f"📢 {special_msg}\n"

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
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) بالدولار:")
    return BUY_PRICE

async def buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",", "."))
        data = user_buy_data[user_id]
        unit = data["unit"]
        amount = float(update.message.text.replace(",", "."))  # سيتم أخذ العدد لاحقًا

        # نفترض أن المستخدم كتب السعر الإجمالي مع العدد، لذا نحسب سعر الوحدة
        # في هذه النسخة نفترض أنه أرسل السعر الإجمالي للـ1 وحدة
        data["total_price"] = total_price

        # جلب الأسعار الحالية
        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        karat = data["karat"]
        current_price = prices[karat][unit]

        profit = current_price - total_price
        color = "🟢" if profit >= 0 else "🔴"
        status = "أرباح" if profit >= 0 else "خسارة"

        await update.message.reply_text(
            f"{color} {status} من شراء الذهب:\n"
            f"عيار الذهب: {karat}\n"
            f"الوحدة: {unit}\n"
            f"السعر الإجمالي للشراء: {total_price} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{status}: {profit:.2f} $"
        )
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

# --- إرسال الأسعار تلقائيًا ---
async def send_prices_job(job_queue):
    from asyncio import sleep
    while True:
        now = datetime.now()
        hour = now.hour
        if 10 <= hour <= 22:  # من 10 صباحًا حتى 10 مساءً
            prices = fetch_gold_prices()
            if prices:
                special_msg = None
                if hour == 10:
                    special_msg = "تم فتح بورصة العراق 📈"
                elif hour == 22:
                    special_msg = "تم إغلاق بورصة العراق 📉"
                message = format_prices_message(prices, special_msg)
                from telegram.constants import ParseMode
                await app.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)
        await sleep(3600)  # كل ساعة

# -------------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # زر حساب الأرباح
    keyboard = [[InlineKeyboardButton("حساب أرباحك 💰", callback_data="buy")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

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

    logging.info("🚀 Gold Bot جاهز للعمل")

    import asyncio
    asyncio.run(send_prices_job(app.job_queue))

    app.run_polling()
