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

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # @channelusername أو -100xxxxxxxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# قاعدة البيانات
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    buy_step TEXT DEFAULT '',
    buy_karat TEXT,
    buy_type TEXT,
    buy_amount REAL,
    buy_price REAL
)
""")
conn.commit()

# =======================
# جلب أسعار الذهب
# =======================
def fetch_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        gram_24k = data.get("price_gram_24k")
        gram_22k = data.get("price_gram_22k")
        gram_21k = data.get("price_gram_21k")
        return {
            "24k": {"gram": gram_24k, "mithqal": gram_24k*5},
            "22k": {"gram": gram_22k, "mithqal": gram_22k*5},
            "21k": {"gram": gram_21k, "mithqal": gram_21k*5},
        }
    except:
        return None

# =======================
# تنسيق رسالة الأسعار
# =======================
def format_prices(prices):
    if not prices:
        return "⚠️ تعذر جلب أسعار الذهب حاليًا. حاول لاحقًا."
    msg = "💰 **أسعار الذهب اليوم** 💰\n\n"
    for karat in ["24k","22k","21k"]:
        msg += f"🔹 **عيار {karat[:-1]}**\n"
        msg += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        msg += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    return msg

# =======================
# أمر /price
# =======================
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    await update.message.reply_text(format_prices(prices), parse_mode="Markdown")

# =======================
# أمر /buy
# =======================
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="buy_24k"),
         InlineKeyboardButton("عيار 22", callback_data="buy_22k"),
         InlineKeyboardButton("عيار 21", callback_data="buy_21k")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    user_id = update.message.from_user.id
    cursor.execute("UPDATE users SET buy_step='' WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text("اختر العيار الذي اشتريت منه الذهب:", reply_markup=reply_markup)

# =======================
# معالجة الأزرار
# =======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("buy_"):
        karat = query.data.split("_")[1]
        cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
        cursor.execute("UPDATE users SET buy_step='type', buy_karat=? WHERE user_id=?", (karat, user_id))
        conn.commit()

        keyboard = [
            [InlineKeyboardButton("غرام", callback_data="buy_type_gram"),
             InlineKeyboardButton("مثقال", callback_data="buy_type_mithqal")]
        ]
        await query.edit_message_text("اختر وحدة الوزن:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("buy_type_"):
        unit = query.data.split("_")[2]
        cursor.execute("UPDATE users SET buy_step='amount', buy_type=? WHERE user_id=?", (unit, user_id))
        conn.commit()
        await query.edit_message_text(f"أرسل الآن عدد {unit} التي اشتريتها:")

# =======================
# معالجة الرسائل أثناء /buy
# =======================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute("SELECT buy_step, buy_karat, buy_type, buy_amount, buy_price FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return
    step, karat, unit, amount, price = row
    text = update.message.text.strip()

    prices = fetch_gold_prices()
    if not prices:
        await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا.")
        return

    if step == "amount":
        try:
            val = float(text)
        except:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح.")
            return
        cursor.execute("UPDATE users SET buy_step='price', buy_amount=? WHERE user_id=?", (val, user_id))
        conn.commit()
        await update.message.reply_text(f"أرسل الآن سعر الشراء لكل {unit} بالـ $:")

    elif step == "price":
        try:
            val = float(text)
        except:
            await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح.")
            return
        cursor.execute("UPDATE users SET buy_price=?, buy_step='' WHERE user_id=?", (val, user_id))
        conn.commit()

        # حساب الأرباح/الخسارة
        cursor.execute("SELECT buy_karat, buy_type, buy_amount, buy_price FROM users WHERE user_id=?", (user_id,))
        karat, unit, amount, buy_price = cursor.fetchone()
        current_price = prices[karat][unit]
        total_buy = amount * buy_price
        total_current = amount * current_price
        profit_loss = total_current - total_buy
        color = "🟢" if profit_loss >=0 else "🔴"
        await update.message.reply_text(
            f"💰 **حساب الأرباح/الخسارة** 💰\n"
            f"العيار: {karat}\n"
            f"الوحدة: {unit}\n"
            f"الكمية: {amount}\n"
            f"سعر الشراء: {buy_price}\n"
            f"السعر الحالي: {current_price}\n"
            f"{color} الفرق: {profit_loss:.2f} $", parse_mode="Markdown"
        )

# =======================
# تشغيل البوت
# =======================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
