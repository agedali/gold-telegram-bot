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
    MessageHandler,
    ConversationHandler,
    filters,
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @channelusername أو -100xxxxxxxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# روابط الشركاء
AFFILIATE_LINKS = [
    {"text": "TPBStar Bot", "url": "https://t.me/TPBStarbot?start=_tgr_pJpcXA9lNjRi"},
    {"text": "Lamazvezdochka Bot", "url": "https://t.me/lamazvezdochkabot?start=_tgr_Xrek0LhhNzUy"}
]

# إعداد قاعدة البيانات
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    subscription TEXT DEFAULT 'free',
    preferred_gram REAL DEFAULT 0,
    preferred_karat TEXT DEFAULT '24k'
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS purchase_price (
    user_id INTEGER,
    karat TEXT,
    unit TEXT,
    amount REAL,
    purchase_price REAL,
    PRIMARY KEY(user_id, karat)
)
""")
conn.commit()

# --- ConversationHandler States ---
SELECT_KARAT, SELECT_UNIT, ENTER_AMOUNT, ENTER_PRICE = range(4)

# --- الأسعار ---
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
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# --- أيام الأسبوع بالعربي ---
ARABIC_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# --- رسالة الأسعار ---
def format_message(prices: dict):
    today = datetime.now()
    day_name = ARABIC_DAYS[today.weekday()]
    date_str = today.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day_name} {date_str}** 💰\n\n"
    for karat in ["24k", "22k", "21k"]:
        prev = 0
        current = prices[karat]["gram"]
        color = "🟢" if current >= prev else "🔴"
        message += f"{color} **عيار {karat[:-1]}**\n- الغرام: `{current:.2f}` $\n- المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    message += "💎 يمكنك حساب أرباحك من الذهب عبر الضغط على الزر أدناه.\n"
    return message

# --- إرسال الأسعار ---
async def send_gold_prices(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    if not prices:
        return
    cursor.execute("SELECT user_id, subscription, preferred_karat, preferred_gram FROM users")
    users = cursor.fetchall()
    for user in users:
        user_id, subscription, karat, preferred_gram = user
        if preferred_gram > 0:
            current_price = prices[karat]["gram"]
            if abs(current_price - preferred_gram)/preferred_gram >= 0.01:
                color = "🟢" if current_price >= preferred_gram else "🔴"
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"{color} **تنبيه سعر الذهب {karat.upper()}**\nالسعر الحالي: `{current_price:.2f}` $\nالاشتراك يتيح لك متابعة التنبيهات.",
                    parse_mode="Markdown"
                )
                cursor.execute("UPDATE users SET preferred_gram=? WHERE user_id=?", (current_price, user_id))
                conn.commit()

# --- أمر /price ---
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()

    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="24k"),
         InlineKeyboardButton("عيار 22", callback_data="22k"),
         InlineKeyboardButton("عيار 21", callback_data="21k")],
        [InlineKeyboardButton("حساب أرباحك من الذهب /buy", callback_data="buy")],
    ]
    for link in AFFILIATE_LINKS:
        keyboard.append([InlineKeyboardButton(link["text"], url=link["url"])])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(format_message(fetch_gold_prices()), reply_markup=reply_markup, parse_mode="Markdown")

# --- ConversationHandler: /buy ---
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("24k", callback_data="24k")],
        [InlineKeyboardButton("22k", callback_data="22k")],
        [InlineKeyboardButton("21k", callback_data="21k")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
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
    await query.edit_message_text("اختر الوحدة:", reply_markup=reply_markup)
    return SELECT_UNIT

async def select_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['unit'] = query.data
    await query.edit_message_text(f"أدخل عدد {query.data}:")
    return ENTER_AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        context.user_data['amount'] = amount
        await update.message.reply_text("الآن أدخل سعر الشراء الإجمالي بالـ $:")
        return ENTER_PRICE
    except:
        await update.message.reply_text("⚠️ أدخل قيمة رقمية صحيحة للكمية.")
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

        await update.message.reply_text(
            f"✅ تم حفظ شراء الذهب:\n"
            f"عيار: {karat}\n"
            f"الوحدة: {unit}\n"
            f"الكمية: {amount}\n"
            f"سعر الوحدة: {unit_price:.2f} $"
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("⚠️ أدخل قيمة رقمية صحيحة للسعر.")
        return ENTER_PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- Main ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("price", price_command))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('buy', buy_command)],
        states={
            SELECT_KARAT: [CallbackQueryHandler(select_karat)],
            SELECT_UNIT: [CallbackQueryHandler(select_unit)],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            ENTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_price)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_handler)

    # إرسال تحديث تلقائي كل ساعة
    app.job_queue.run_repeating(send_gold_prices, interval=3600, first=0)

    logging.info("🚀 Gold Bot بدأ ويعمل مع تحديث تلقائي كل ساعة وأمر /price")
    app.run_polling()
