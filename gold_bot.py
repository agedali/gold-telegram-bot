import logging
import os
import requests
from datetime import datetime, time as dt_time
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
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # القناة أو معرفك الشخصي لتجربة الرسائل
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")
YOUR_USER_ID = int(os.getenv("YOUR_USER_ID", "0"))  # لتجربة إرسال الرسالة مباشرة عند التشغيل

# ----------------- مراحل حساب الأرباح -----------------
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_PRICE = range(4)
user_buy_data = {}

# ----------------- خريطة الأيام بالعربي -----------------
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# ----------------- دالة جلب أسعار الذهب -----------------
def fetch_gold_prices():
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

# ----------------- دالة تنسيق الرسائل -----------------
def format_prices_message(prices, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    if special_msg:
        message += f"📢 {special_msg}\n\n"
    for karat in ["24k","22k","21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n"
    if prices.get("ounce"):
        message += f"🔹 الأونصة: `{prices['ounce']:.2f}` $\n"
    message += "\n💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return message

# ----------------- وظائف حساب الأرباح -----------------
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
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء ({user_buy_data[user_id]['unit']}):")
    return BUY_PRICE

async def buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",", "."))
        data = user_buy_data[user_id]
        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
            return ConversationHandler.END

        karat = data["karat"]
        unit = data["unit"]
        # حساب سعر الوحدة
        if unit == "gram":
            amount = prices[karat]["gram"]  # فقط لاستخدام كمية الوحدة
        else:
            amount = prices[karat]["mithqal"]

        # هنا نعتبر عدد الوحدات من السعر الإجمالي / السعر الحالي للوحدة
        # ولكن المستخدم أرسل السعر الإجمالي لعدد محدد، لذا نفترض أن amount = إجمالي الوحدات
        # يمكن تعديل الحساب وفق ما تريد
        units_count = 1  # بما أن المستخدم أرسل السعر الإجمالي لعدد محدد، نترك 1 للوحدة

        buy_price_per_unit = total_price / units_count
        current_price_per_unit = prices[karat][unit]

        profit = current_price_per_unit - buy_price_per_unit

        if profit >= 0:
            text = f"💰 ربح: {profit:.2f} $"
        else:
            text = f"🔴 خسارة: {abs(profit):.2f} $"

        msg = (
            f"💎 **حساب أرباحك** 💎\n"
            f"عيار الذهب: {karat}\n"
            f"الوحدة: {unit}\n"
            f"السعر الإجمالي: {total_price:.2f} $\n"
            f"السعر الحالي: {current_price_per_unit:.2f} $\n"
            f"{text}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
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

# ----------------- إرسال الأسعار التلقائي -----------------
async def send_prices(context: ContextTypes.DEFAULT_TYPE, special_msg=None):
    prices = fetch_gold_prices()
    if not prices:
        logging.warning("⚠️ تعذر جلب أسعار الذهب.")
        return
    message = format_prices_message(prices, special_msg)
    await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

# ----------------- دالة بدء التشغيل -----------------
async def start_sending_initial(app):
    # إرسال فوراً عند التشغيل للمستخدم نفسه
    prices = fetch_gold_prices()
    if prices and YOUR_USER_ID:
        message = format_prices_message(prices)
        await app.bot.send_message(chat_id=YOUR_USER_ID, text=message, parse_mode="Markdown")

# ----------------- Main -----------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ---- حساب الأرباح ----
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_button, pattern="^buy$")],
        states={
            BUY_KARAT: [CallbackQueryHandler(buy_karat, pattern="^(24k|22k|21k)$")],
            BUY_UNIT: [CallbackQueryHandler(buy_unit, pattern="^(gram|mithqal)$")],
            BUY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_price)],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel)],
    )
    app.add_handler(conv_handler)

    # ---- جدولة الأسعار كل ساعة من 10 صباحًا إلى 10 مساءً ----
    from datetime import timedelta
    job_queue = app.job_queue
    for hour in range(10, 23):
        job_queue.run_daily(lambda context: send_prices(context,
                                                        special_msg="تم فتح بورصة العراق" if hour==10 else
                                                                     "تم إغلاق بورصة العراق" if hour==22 else None),
                            time=dt_time(hour, 0, 0))

    # ---- إرسال الرسالة فوراً عند التشغيل ----
    import asyncio
    asyncio.run(start_sending_initial(app))

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
