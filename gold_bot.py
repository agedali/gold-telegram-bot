import logging
import os
import requests
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)
from datetime import datetime

# --- إعداد اللوج ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- مفاتيح البيئة ---
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOLDPRICEZ_API_KEY = os.getenv("GOLDPRICEZ_API_KEY")  # ضع مفتاحك هنا

# --- قاعدة البيانات ---
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    buy_karat TEXT,
    buy_unit TEXT,
    buy_amount REAL,
    buy_price REAL
)
""")
conn.commit()

# --- المراحل لحساب الأرباح ---
SELECT_KARAT, SELECT_UNIT, ENTER_AMOUNT, ENTER_PRICE = range(4)

# --- دالة لجلب أسعار الذهب ---
def fetch_gold_prices():
    url = "https://goldpricez.com/api/rates/currency/usd/measure/all"
    headers = {"X-API-KEY": GOLDPRICEZ_API_KEY}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        # أسعار الغرام والمثقال والأونصة
        gram = float(data["gram_in_usd"])
        ounce = float(data["ounce_price_usd"])
        mithqal = gram * 5
        return {"gram": gram, "mithqal": mithqal, "ounce": ounce}
    except Exception as e:
        logging.error(f"Error fetching gold prices: {e}")
        return None

# --- أمر /price ---
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    if not prices:
        await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا. حاول لاحقًا.")
        return
    # التاريخ والوقت بالعربي
    days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    today = datetime.now()
    day_name = days_ar[today.weekday()]
    date_str = today.strftime("%d-%m-%Y")
    
    message = (
        f"💰 **أسعار الذهب اليوم - {day_name} {date_str}** 💰\n\n"
        f"🔹 الغرام: `{prices['gram']:.2f}` $\n"
        f"🔹 المثقال: `{prices['mithqal']:.2f}` $\n"
        f"🔹 الأونصة: `{prices['ounce']:.2f}` $"
    )
    
    keyboard = [
        [InlineKeyboardButton("حساب أرباحك من الذهب 💰", callback_data="buy")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")

# --- بدء حساب الأرباح ---
async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="24k"),
         InlineKeyboardButton("عيار 22", callback_data="22k"),
         InlineKeyboardButton("عيار 21", callback_data="21k")]
    ]
    await query.edit_message_text("اختر العيار الذي اشتريت به الذهب:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_KARAT

async def select_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["buy_karat"] = query.data
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="gram"),
         InlineKeyboardButton("مثقال", callback_data="mithqal")]
    ]
    await query.edit_message_text("اختر الوحدة التي قمت بشرائها بها:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_UNIT

async def select_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["buy_unit"] = query.data
    await query.edit_message_text(f"أدخل عدد {query.data} التي اشتريت بها الذهب:")
    return ENTER_AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        context.user_data["buy_amount"] = amount
        await update.message.reply_text("أدخل سعر الشراء لكل وحدة بالدولار:")
        return ENTER_PRICE
    except:
        await update.message.reply_text("⚠️ يرجى إدخال رقم صالح لعدد الغرامات أو المثقال.")
        return ENTER_AMOUNT

async def enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
        context.user_data["buy_price"] = price
        
        # حفظ بيانات المستخدم في DB
        user_id = update.message.from_user.id
        cursor.execute("""
            INSERT OR REPLACE INTO users(user_id, buy_karat, buy_unit, buy_amount, buy_price)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, context.user_data["buy_karat"], context.user_data["buy_unit"],
              context.user_data["buy_amount"], context.user_data["buy_price"]))
        conn.commit()
        
        # حساب الأرباح والخسائر
        prices = fetch_gold_prices()
        if not prices:
            await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب الحالي لحساب الربح.")
            return ConversationHandler.END
        
        unit = context.user_data["buy_unit"]
        amount = context.user_data["buy_amount"]
        buy_price = context.user_data["buy_price"]
        current_price = prices[unit]
        
        profit_loss = (current_price - buy_price) * amount
        if profit_loss > 0:
            msg = f"🟢 ربحك الحالي: ${profit_loss:.2f}"
        elif profit_loss < 0:
            msg = f"🔴 خسارتك الحالية: ${-profit_loss:.2f}"
        else:
            msg = "⚪ لا يوجد ربح أو خسارة حالياً."
        
        await update.message.reply_text(f"✅ تم حساب أرباحك:\n{msg}")
        return ConversationHandler.END
    except:
        await update.message.reply_text("⚠️ يرجى إدخال رقم صالح لسعر الشراء.")
        return ENTER_PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- التشغيل الرئيسي ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # /price
    app.add_handler(CommandHandler("price", price_command))
    
    # حساب الأرباح
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_start, pattern="buy")],
        states={
            SELECT_KARAT: [CallbackQueryHandler(select_karat)],
            SELECT_UNIT: [CallbackQueryHandler(select_unit)],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            ENTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_price)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)

    logging.info("🚀 Gold Bot بدأ ويعمل")
    app.run_polling()
