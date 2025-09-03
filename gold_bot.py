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
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# متغيرات البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# قاعدة البيانات
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    step TEXT DEFAULT '',
    buy_karat TEXT DEFAULT '',
    buy_unit TEXT DEFAULT '',
    buy_amount REAL DEFAULT 0,
    buy_price REAL DEFAULT 0
)
""")
conn.commit()

# ========== جلب أسعار الذهب ==========
def fetch_gold_prices():
    """جلب أسعار الذهب من GoldAPI"""
    try:
        url = "https://www.goldapi.io/api/XAU/USD"
        headers = {"x-access-token": GOLDAPI_KEY}
        response = requests.get(url, headers=headers)
        data = response.json()

        if "price_gram_24k" not in data:
            logging.error(f"❌ API response missing data: {data}")
            return None

        gram_24k = data["price_gram_24k"]
        gram_22k = data["price_gram_22k"]
        gram_21k = data["price_gram_21k"]

        return {
            "24k": {"gram": gram_24k, "mithqal": gram_24k * 5},
            "22k": {"gram": gram_22k, "mithqal": gram_22k * 5},
            "21k": {"gram": gram_21k, "mithqal": gram_21k * 5},
        }

    except Exception as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# ========== منطق الربح والخسارة ==========
def calculate_profit_loss(buy_price, current_price, amount):
    diff = (current_price - buy_price) * amount
    if diff > 0:
        return f"🟢 لديك ربح قدره: {diff:.2f} $"
    elif diff < 0:
        return f"🔴 لديك خسارة قدرها: {abs(diff):.2f} $"
    else:
        return "⚖️ لا يوجد ربح ولا خسارة."

# ========== الأوامر ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()

    keyboard = [
        [InlineKeyboardButton("💰 حساب أرباحك من الذهب", callback_data="buy_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("مرحباً 👋\nاستخدم الزر أدناه لحساب أرباحك أو خسارتك من الذهب:", reply_markup=reply_markup)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /buy يبدأ عملية الحساب"""
    user_id = update.message.from_user.id
    cursor.execute("UPDATE users SET step='choose_karat' WHERE user_id=?", (user_id,))
    conn.commit()

    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="karat_24k")],
        [InlineKeyboardButton("عيار 22", callback_data="karat_22k")],
        [InlineKeyboardButton("عيار 21", callback_data="karat_21k")],
    ]
    await update.message.reply_text("اختر العيار الذي اشتريت منه:", reply_markup=InlineKeyboardMarkup(keyboard))

# ========== الأزرار ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy_start":
        cursor.execute("UPDATE users SET step='choose_karat' WHERE user_id=?", (user_id,))
        conn.commit()
        keyboard = [
            [InlineKeyboardButton("عيار 24", callback_data="karat_24k")],
            [InlineKeyboardButton("عيار 22", callback_data="karat_22k")],
            [InlineKeyboardButton("عيار 21", callback_data="karat_21k")],
        ]
        await query.edit_message_text("اختر العيار الذي اشتريت منه:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("karat_"):
        karat = query.data.split("_")[1]
        cursor.execute("UPDATE users SET buy_karat=?, step='choose_unit' WHERE user_id=?", (karat, user_id))
        conn.commit()
        keyboard = [
            [InlineKeyboardButton("غرام", callback_data="unit_gram")],
            [InlineKeyboardButton("مثقال", callback_data="unit_mithqal")],
        ]
        await query.edit_message_text("اختر الوحدة:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("unit_"):
        unit = query.data.split("_")[1]
        cursor.execute("UPDATE users SET buy_unit=?, step='enter_amount' WHERE user_id=?", (unit, user_id))
        conn.commit()
        await query.edit_message_text("✍️ أدخل الكمية (عدد الغرامات أو المثاقيل):")

# ========== إدخال النص ==========
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    cursor.execute("SELECT step, buy_unit, buy_karat, buy_amount, buy_price FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()

    if not user:
        return

    step, buy_unit, buy_karat, buy_amount, buy_price = user

    if step == "enter_amount":
        try:
            amount = float(text)
            cursor.execute("UPDATE users SET buy_amount=?, step='enter_price' WHERE user_id=?", (amount, user_id))
            conn.commit()
            await update.message.reply_text("✍️ أدخل سعر الشراء (بالدولار):")
        except ValueError:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح.")

    elif step == "enter_price":
        try:
            price = float(text)
            cursor.execute("UPDATE users SET buy_price=?, step='done' WHERE user_id=?", (price, user_id))
            conn.commit()

            # حساب الربح والخسارة
            prices = fetch_gold_prices()
            if not prices:
                await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
                return

            current_price = prices[buy_karat]["gram"] if buy_unit == "gram" else prices[buy_karat]["mithqal"]
            result = calculate_profit_loss(buy_price, current_price, buy_amount)

            await update.message.reply_text(
                f"🔎 تفاصيل العملية:\n"
                f"- العيار: {buy_karat}\n"
                f"- الوحدة: {buy_unit}\n"
                f"- الكمية: {buy_amount}\n"
                f"- سعر الشراء: {buy_price:.2f} $\n"
                f"- السعر الحالي: {current_price:.2f} $\n\n"
                f"{result}"
            )
        except ValueError:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح.")

# ========== تشغيل البوت ==========
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logging.info("🚀 Gold Bot يعمل الآن...")
    app.run_polling()
