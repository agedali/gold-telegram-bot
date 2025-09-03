import logging
import os
import requests
import sqlite3
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS purchase_price (
    user_id INTEGER,
    karat TEXT,
    purchase_price REAL,
    unit TEXT,
    amount REAL,
    PRIMARY KEY(user_id, karat)
)
""")
conn.commit()

# Conversation steps
SELECT_KARAT, SELECT_UNIT, ENTER_AMOUNT, ENTER_PRICE = range(4)

ARABIC_DAYS = {
    0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء",
    3: "الخميس", 4: "الجمعة", 5: "السبت", 6: "الأحد"
}

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
        }
    except:
        return None

def format_message(prices: dict):
    now = datetime.now()
    day = ARABIC_DAYS[now.weekday()]
    date = now.strftime("%d/%m/%Y")
    msg = f"💰 **أسعار الذهب اليوم - {day} {date}** 💰\n\n"
    for karat in ["24k","22k","21k"]:
        msg += f"🟢 **عيار {karat[:-1]}**\n- الغرام: `{prices[karat]['gram']:.2f}` $\n- المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    msg += "💎 ميزات متاحة للجميع:\n- حساب أرباحك من الذهب\n\nاختر زرًا أدناه."
    return msg

# ================== /price ==================
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="show_24k"),
         InlineKeyboardButton("عيار 22", callback_data="show_22k"),
         InlineKeyboardButton("عيار 21", callback_data="show_21k")],
        [InlineKeyboardButton("حساب أرباحك من الذهب 💰", callback_data="start_buy")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(format_message(prices), reply_markup=reply_markup, parse_mode="Markdown")

async def show_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prices = fetch_gold_prices()
    key = query.data.replace("show_", "")
    selected = prices[key]
    await query.edit_message_text(
        f"🟢 **سعر الذهب - {key.upper()}**\n"
        f"- الغرام: `{selected['gram']:.2f}` $\n"
        f"- المثقال: `{selected['mithqal']:.2f}` $",
        parse_mode="Markdown"
    )

# ================== ConversationHandler للأرباح ==================
async def start_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if update.callback_query else None
    keyboard = [
        [InlineKeyboardButton("24k", callback_data="24k")],
        [InlineKeyboardButton("22k", callback_data="22k")],
        [InlineKeyboardButton("21k", callback_data="21k")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.answer()
        await query.edit_message_text("اختر العيار الذي قمت بشرائه:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("اختر العيار الذي قمت بشرائه:", reply_markup=reply_markup)
    return SELECT_KARAT

async def select_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['karat'] = query.data
    keyboard = [
        [InlineKeyboardButton("غرام", callback_data="gram")],
        [InlineKeyboardButton("مثقال", callback_data="mithqal")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر الوحدة التي اشتريت بها الذهب:", reply_markup=reply_markup)
    return SELECT_UNIT

async def select_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['unit'] = query.data
    await query.edit_message_text(f"أدخل كمية الذهب بالـ {query.data}:")
    return ENTER_AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        context.user_data['amount'] = amount
        await update.message.reply_text("أدخل سعر الشراء الإجمالي بالدولار (السعر الذي دفعته للكمية):")
        return ENTER_PRICE
    except:
        await update.message.reply_text("⚠️ أدخل قيمة رقمية صحيحة للكمية:")
        return ENTER_AMOUNT

async def enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        total_price = float(update.message.text)
        karat = context.user_data['karat']
        unit = context.user_data['unit']
        amount = context.user_data['amount']
        unit_price = total_price / amount

        cursor.execute("""
            INSERT OR REPLACE INTO purchase_price(user_id, karat, purchase_price, unit, amount)
            VALUES (?, ?, ?, ?, ?)
        """, (update.message.from_user.id, karat, unit_price, unit, amount))
        conn.commit()

        prices = fetch_gold_prices()
        current_price = prices[karat][unit]
        profit_loss = (current_price - unit_price) * amount
        status = "ربح" if profit_loss >= 0 else "خسارة"

        await update.message.reply_text(
            f"✅ تم حفظ شراء الذهب:\n"
            f"عيار: {karat}\n"
            f"الوحدة: {unit}\n"
            f"الكمية: {amount}\n"
            f"سعر الوحدة: {unit_price:.2f} $\n\n"
            f"💹 السعر الحالي: {current_price:.2f} $\n"
            f"📊 {status}: {abs(profit_loss):.2f} $"
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("⚠️ أدخل قيمة رقمية صحيحة للسعر.")
        return ENTER_PRICE

# ================== Main ==================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_buy, pattern="start_buy"),
                      CommandHandler("buy", start_buy)],
        states={
            SELECT_KARAT: [CallbackQueryHandler(select_karat)],
            SELECT_UNIT: [CallbackQueryHandler(select_unit)],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            ENTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_price)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("price", price_command))
    # Handler خاص بعرض الأسعار بدون التعارض
    app.add_handler(CallbackQueryHandler(show_price, pattern="show_.*"))
    app.add_handler(conv_handler)

    logging.info("🚀 Gold Bot بدأ ويعمل")
    app.run_polling()
