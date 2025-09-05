import logging
import os
import requests
import sqlite3
from datetime import datetime, time, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# خريطة الأيام بالعربي
days_ar = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# قاعدة بيانات لتخزين بيانات المستخدم
conn = sqlite3.connect("users.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    karat TEXT,
    unit TEXT,
    amount REAL,
    total_price REAL
)
""")
conn.commit()


def fetch_gold_prices():
    """جلب الأسعار اللحظية من GoldAPI"""
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "ounce": data.get("price"),
            "24k": {"gram": data.get("price_gram_24k"), "mithqal": data.get("price_gram_24k") * 5},
            "22k": {"gram": data.get("price_gram_22k"), "mithqal": data.get("price_gram_22k") * 5},
            "21k": {"gram": data.get("price_gram_21k"), "mithqal": data.get("price_gram_21k") * 5},
        }
    except Exception as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None


def format_prices_message(prices: dict, profits: str = ""):
    """تنسيق رسالة الأسعار مع التاريخ"""
    now = datetime.now()
    day = days_ar[now.weekday()]
    date_str = now.strftime("%d/%m/%Y %H:%M")

    message = f"💰 **أسعار الذهب اليوم - {day} {date_str}** 💰\n\n"
    message += f"🔸 الأونصة: `{prices['ounce']:.2f}` $\n\n"

    for karat in ["24k", "22k", "21k"]:
        message += f"🔹 عيار {karat[:-1]}:\n"
        message += f"   - الغرام: `{prices[karat]['gram']:.2f}` $\n"
        message += f"   - المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"

    if profits:
        message += profits + "\n"

    return message


def calc_profit(user_id: int, prices: dict):
    """حساب أرباح المستخدم إن وجدت بياناته"""
    cur.execute("SELECT karat, unit, amount, total_price FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        return ""

    karat, unit, amount, total_price = row
    buy_price_per_unit = total_price / amount
    current_price = prices[karat][unit]
    profit = (current_price - buy_price_per_unit) * amount

    if profit >= 0:
        status = f"✅ **ربح**: `{profit:.2f}$`"
    else:
        status = f"❌ **خسارة**: `{profit:.2f}$`"

    return (
        f"\n📊 حساب أرباحك:\n"
        f"عيار الذهب: {karat}\n"
        f"الوحدة: {unit}\n"
        f"الكمية: {amount}\n"
        f"إجمالي الشراء: {total_price}$\n"
        f"{status}"
    )


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدخال بيانات الشراء"""
    try:
        # مثال: /buy 21k gram 40 3200
        _, karat, unit, amount, total_price = update.message.text.split()
        amount = float(amount)
        total_price = float(total_price)

        cur.execute(
            "REPLACE INTO users (user_id, karat, unit, amount, total_price) VALUES (?, ?, ?, ?, ?)",
            (update.message.from_user.id, karat, unit, amount, total_price),
        )
        conn.commit()

        await update.message.reply_text(
            f"✅ تم حفظ بياناتك:\n"
            f"عيار: {karat}\nوحدة: {unit}\nكمية: {amount}\nإجمالي الشراء: {total_price}$"
        )
    except Exception:
        await update.message.reply_text("⚠️ الصيغة الصحيحة: `/buy 21k gram 40 3200`", parse_mode="Markdown")


async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    """إرسال الأسعار للمستخدمين كل 3 ساعات"""
    prices = fetch_gold_prices()
    if not prices:
        return

    now = datetime.now().time()
    open_time = time(10, 0)
    close_time = time(17, 0)

    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()

    for (user_id,) in users:
        profit_msg = calc_profit(user_id, prices)
        msg = format_prices_message(prices, profit_msg)

        if now.hour == open_time.hour and now.minute < 5:
            msg = "📈 تم فتح بورصة العراق\n\n" + msg
        elif now.hour == close_time.hour and now.minute < 5:
            msg += "\n📉 تم إغلاق بورصة العراق"

        try:
            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"❌ Error sending to {user_id}: {e}")


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # إدخال بيانات الشراء
    app.add_handler(CommandHandler("buy", buy_command))

    # جدولة إرسال الأسعار كل 3 ساعات من 10 ص إلى 5 م
    app.job_queue.run_repeating(send_prices, interval=3 * 3600, first=timedelta(seconds=5))

    logging.info("🚀 Gold Bot جاهز للعمل")
    app.run_polling()
