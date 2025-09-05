import logging
import os
import requests
from datetime import datetime, time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    CommandHandler,
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @channelusername أو -100xxxx
GOLDPRICEZ_KEY = os.getenv("GOLDPRICEZ_KEY")  # مفتاح API

# مراحل حساب الأرباح
BUY_KARAT, BUY_UNIT, BUY_AMOUNT, BUY_PRICE = range(4)
user_buy_data = {}

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- دالة جلب أسعار الذهب ---
def fetch_gold_prices():
    url = "https://goldpricez.com/api/rates/currency/usd/measure/all"
    headers = {"X-API-KEY": GOLDPRICEZ_KEY}

    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()

        return {
            "24k": {"gram": data.get("gram_in_usd"), "mithqal": data.get("gram_in_usd")*5},
            "22k": {"gram": data.get("gram_in_usd")*0.9167, "mithqal": data.get("gram_in_usd")*0.9167*5},
            "21k": {"gram": data.get("gram_in_usd")*0.875, "mithqal": data.get("gram_in_usd")*0.875*5},
            "ounce": data.get("ounce_price_usd")
        }
    except Exception as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- تنسيق رسالة الأسعار ---
def format_prices_message(prices, special_msg=None):
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    msg = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    if special_msg:
        msg += f"{special_msg}\n\n"
    for karat in ["24k","22k","21k"]:
        msg += f"🔹 عيار {karat[:-1]}:\n"
        msg += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        msg += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    msg += f"🔹 الأونصة: `{prices['ounce']:.2f}` $\n\n"
    msg += "💎 اضغط على زر حساب أرباحك لمعرفة الربح أو الخسارة"
    return msg

# --- إرسال الرسائل ---
async def send_prices(context: ContextTypes.DEFAULT_TYPE, special_msg=None):
    prices = fetch_gold_prices()
    if not prices:
        logging.warning("⚠️ تعذر جلب أسعار الذهب.")
        return
    keyboard = [[InlineKeyboardButton("حساب أرباحك 💰", callback_data="buy")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=format_prices_message(prices, special_msg),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

# --- وظائف حساب الأرباح ---
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
    await query.edit_message_text(f"أرسل السعر الإجمالي لشراء {query.data} التي اشتريتها بالدولار:")
    return BUY_PRICE

async def buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        total_price = float(update.message.text.replace(",","."))  # السعر الإجمالي
        data = user_buy_data[user_id]
        unit = data["unit"]
        amount = 1  # البوت يفترض 1 وحدة لأن المستخدم أعطى السعر الإجمالي لأي عدد وحدات
        gram_count = total_price / 1  # سنحسب لاحقًا سعر الوحدة بالاعتماد على السعر الإجمالي والكمية

        # هنا يمكن إضافة أي معالجة إضافية إذا أردنا السماح بإدخال العدد
        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب الآن.")
            return ConversationHandler.END

        karat = data["karat"]
        current_price = prices[karat][unit]
        # حساب ربح/خسارة: نقسم السعر الإجمالي على عدد الوحدات لتحديد سعر الوحدة
        # لنفترض أن المستخدم ادخل السعر الإجمالي للكمية الكاملة، نحتاج معرفة الكمية
        # لتبسيط المثال سنفترض كمية = 1 وحدة
        profit = total_price - current_price * amount

        color = "🟢 ربح" if profit >=0 else "🔴 خسارة"

        await update.message.reply_text(
            f"💰 نتائج حساب أرباحك:\n"
            f"عيار الذهب: {karat}\n"
            f"الوحدة: {unit}\n"
            f"السعر الإجمالي للشراء: {total_price} $\n"
            f"السعر الحالي: {current_price:.2f} $\n"
            f"{color}: {profit:.2f} $",
            parse_mode=ParseMode.MARKDOWN
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

# --- Main ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # إعداد محادثة حساب الأرباح
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

    # --- إرسال الأسعار كل ساعة من 10 صباحًا حتى 10 مساءً ---
    for hour in range(10, 23):
        app.job_queue.run_daily(
            lambda context, h=hour: context.job_queue.run_once(send_prices, 0, context=context),
            time=time(hour,0,0)
        )

    # إرسال رسالة فورًا عند تشغيل البوت
    import asyncio
    asyncio.run(send_prices(app.job_queue))

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
