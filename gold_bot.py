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
from datetime import datetime

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# إعداد قاعدة البيانات
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    step TEXT DEFAULT NULL,
    buy_karat TEXT DEFAULT NULL,
    buy_unit TEXT DEFAULT NULL,
    buy_quantity REAL DEFAULT NULL,
    buy_price REAL DEFAULT NULL
)
""")
conn.commit()


def fetch_gold_prices():
    """تجلب أسعار الذهب من GoldAPI"""
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
            "24k": {"gram": gram_24k, "mithqal": gram_24k * 5},
            "22k": {"gram": gram_22k, "mithqal": gram_22k * 5},
            "21k": {"gram": gram_21k, "mithqal": gram_21k * 5},
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None


def format_prices_message(prices):
    """عرض الأسعار مع التاريخ اليومي"""
    if not prices:
        return "⚠️ تعذر جلب أسعار الذهب حاليًا. حاول لاحقًا."
    now = datetime.now()
    weekdays_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    day_name = weekdays_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day_name} {date_str}** 💰\n\n"
    for karat in ["24k", "22k", "21k"]:
        message += f"🔹 **عيار {karat[:-1]}**\n- الغرام: `{prices[karat]['gram']:.2f}` $\n- المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    message += "لـ حساب أرباحك من الذهب اضغط على الزر أدناه 👇"
    return message


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start"""
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()
    await price_command(update, context)


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /price"""
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()

    prices = fetch_gold_prices()
    keyboard = [[InlineKeyboardButton("💰 حساب أرباحك من الذهب", callback_data="buy")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(format_prices_message(prices), reply_markup=reply_markup, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغط الأزرار"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy":
        cursor.execute("UPDATE users SET step='choose_karat' WHERE user_id=?", (user_id,))
        conn.commit()
        keyboard = [
            [InlineKeyboardButton("عيار 24", callback_data="24k"),
             InlineKeyboardButton("عيار 22", callback_data="22k"),
             InlineKeyboardButton("عيار 21", callback_data="21k")],
        ]
        await query.edit_message_text("اختر عيار الذهب الذي اشتريته:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data in ["24k", "22k", "21k"]:
        cursor.execute("UPDATE users SET buy_karat=?, step='choose_unit' WHERE user_id=?", (query.data, user_id))
        conn.commit()
        keyboard = [
            [InlineKeyboardButton("غرام", callback_data="gram"),
             InlineKeyboardButton("مثقال", callback_data="mithqal")],
        ]
        await query.edit_message_text("اختر وحدة القياس التي اشتريت بها الذهب:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data in ["gram", "mithqal"]:
        cursor.execute("UPDATE users SET buy_unit=?, step='enter_quantity' WHERE user_id=?", (query.data, user_id))
        conn.commit()
        await query.edit_message_text(f"الآن، أدخل عدد {query.data} الذي اشتريته:")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية للمراحل المختلفة"""
    user_id = update.message.from_user.id
    text = update.message.text
    cursor.execute("SELECT step, buy_karat, buy_unit, buy_quantity FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return
    step, buy_karat, buy_unit, buy_quantity = row

    if step == "enter_quantity":
        try:
            quantity = float(text.replace(",", "."))
            cursor.execute("UPDATE users SET buy_quantity=?, step='enter_price' WHERE user_id=?", (quantity, user_id))
            conn.commit()
            await update.message.reply_text(f"✅ تم حفظ الكمية: {quantity} {buy_unit}\nالآن، أدخل سعر الشراء لكل {buy_unit}:")
        except ValueError:
            await update.message.reply_text("⚠️ يرجى إدخال رقم صحيح للكمية.")

    elif step == "enter_price":
        try:
            price = float(text.replace(",", "."))
            cursor.execute("UPDATE users SET buy_price=?, step=NULL WHERE user_id=?", (price, user_id))
            conn.commit()

            # حساب الربح/الخسارة
            prices = fetch_gold_prices()
            if not prices:
                await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا. حاول لاحقًا.")
                return

            current_price = prices[buy_karat][buy_unit]
            profit = (current_price - price) * buy_quantity
            profit_sign = "🟢 ربح" if profit >= 0 else "🔴 خسارة"
            await update.message.reply_text(
                f"{profit_sign}: {profit:.2f} $\n"
                f"- سعر الشراء لكل {buy_unit}: {price:.2f} $\n"
                f"- السعر الحالي لكل {buy_unit}: {current_price:.2f} $\n"
                f"- الكمية: {buy_quantity} {buy_unit}"
            )
        except ValueError:
            await update.message.reply_text("⚠️ يرجى إدخال رقم صحيح لسعر الشراء.")


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logging.info("🚀 Gold Bot بدأ ويعمل مع /price و زر حساب الأرباح")
    app.run_polling()
