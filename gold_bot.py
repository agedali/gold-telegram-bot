import logging
import os
import requests
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes
)

# --- إعداد اللوج ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- مفاتيح البيئة ---
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # لمجرد الاستخدام لاحقاً
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# --- مراحل الحساب ---
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_PRICE = range(4)

# --- تخزين بيانات المستخدم أثناء الحساب ---
user_buy_data = {}

# --- خريطة الأيام بالعربي ---
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- جلب أسعار الذهب ---
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "24k": {"gram": data.get("price_gram_24k"), "mithqal": data.get("price_gram_24k")*5, "ounce": data.get("price_ounce")},
            "22k": {"gram": data.get("price_gram_22k"), "mithqal": data.get("price_gram_22k")*5, "ounce": data.get("price_ounce")},
            "21k": {"gram": data.get("price_gram_21k"), "mithqal": data.get("price_gram_21k")*5, "ounce": data.get("price_ounce")},
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- تنسيق رسالة الأسعار ---
def format_prices_message(prices: dict):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    msg = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    for karat in ["24k","22k","21k"]:
        msg += f"🔹 عيار {karat[:-1]}:\n"
        msg += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        msg += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n"
        msg += f"   - الأونصة: `{prices[karat]['ounce']:.2f}` $\n\n"
    msg += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return msg

# --- أمر /price ---
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    if not prices:
        await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا. حاول لاحقًا.")
        return
    keyboard = [[InlineKeyboardButton("حساب أرباحك 💰", callback_data="buy")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(format_prices_message(prices), reply_markup=reply_markup, parse_mode="Markdown")

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
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({query.data}) الذي تم شراؤه بالدولار:")
    return BUY_AMOUNT

async def buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",","."))
        user_buy_data[user_id]["total_price"] = total_price
        await update.message.reply_text("أرسل عدد الوحدات التي اشتريتها (عدد الغرامات أو المثقال):")
        return BUY_PRICE
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح للسعر الإجمالي.")
        return BUY_AMOUNT

async def buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        amount = float(update.message.text.replace(",","."))
        data = user_buy_data[user_id]
        data["amount"] = amount

        # حساب سعر الوحدة
        unit_price = data["total_price"] / amount

        # جلب السعر الحالي
        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        karat = data["karat"]
        unit = data["unit"]
        current_price = prices[karat][unit]

        profit = (current_price - unit_price) * amount
        if profit >= 0:
            color = "🟢 ربح"
        else:
            color = "🔴 خسارة"

        await update.message.reply_text(
            f"💰 نتائج حساب أرباحك:\n"
            f"عيار الذهب: {karat}\n"
            f"الوحدة: {unit}\n"
            f"الكمية: {amount}\n"
            f"السعر الإجمالي للشراء: {data['total_price']} $\n"
            f"سعر الوحدة: {unit_price:.2f} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{color}: {profit:.2f} $"
        )
        user_buy_data.pop(user_id, None)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صالح للكمية.")
        return BUY_PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_buy_data.pop(user_id, None)
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# --- تشغيل البوت ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("price", price_command))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="buy")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_amount)],
            BUY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
