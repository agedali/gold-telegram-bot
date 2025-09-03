import logging
import os
import requests
import sqlite3
import matplotlib.pyplot as plt
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# روابط الشركاء
AFFILIATE_LINKS = [
    {"text": "TPBStar Bot", "url": "https://t.me/TPBStarbot?start=_tgr_pJpcXA9lNjRi"},
    {"text": "Lamazvezdochka Bot", "url": "https://t.me/lamazvezdochkabot?start=_tgr_Xrek0LhhNzUy"}
]

# قاعدة البيانات
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    preferred_karat TEXT DEFAULT '24k',
    last_price REAL DEFAULT 0
)
""")
conn.commit()

# لجمع بيانات الأسعار للرسم البياني
price_history = {
    "24k": [],
    "22k": [],
    "21k": []
}

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

        # حفظ التاريخ للرسم البياني
        for k, price in zip(["24k","22k","21k"], [gram_24k, gram_22k, gram_21k]):
            price_history[k].append(price)
            if len(price_history[k]) > 20:  # آخر 20 تحديث فقط
                price_history[k].pop(0)

        return {
            "24k": gram_24k,
            "22k": gram_22k,
            "21k": gram_21k
        }
    except:
        return None

def generate_chart(karat):
    """رسم بياني لآخر 20 سعر"""
    plt.figure(figsize=(6,3))
    plt.plot(price_history[karat], marker='o')
    plt.title(f"سعر الذهب - {karat}")
    plt.ylabel("USD/غرام")
    plt.grid(True)
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

async def send_price_alerts(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    if not prices:
        return

    cursor.execute("SELECT user_id, preferred_karat, last_price FROM users")
    for user_id, karat, last_price in cursor.fetchall():
        current = prices[karat]
        if last_price == 0 or abs(current - last_price)/last_price >= 0.01:  # تغير >= 1%
            color = "🟢" if current >= last_price else "🔴"
            await context.bot.send_message(
                chat_id=user_id,
                text=f"{color} **تنبيه سعر الذهب {karat.upper()}**\nالسعر الحالي: `{current:.2f}` $",
                parse_mode="Markdown"
            )
            # تحديث السعر الأخير
            cursor.execute("UPDATE users SET last_price=? WHERE user_id=?", (current, user_id))
            conn.commit()

            # إرسال الرسم البياني
            chart = generate_chart(karat)
            await context.bot.send_photo(chat_id=user_id, photo=chart)

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()

    prices = fetch_gold_prices()
    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="24k"),
         InlineKeyboardButton("عيار 22", callback_data="22k"),
         InlineKeyboardButton("عيار 21", callback_data="21k")]
    ]
    for link in AFFILIATE_LINKS:
        keyboard.append([InlineKeyboardButton(link["text"], url=link["url"])])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"💰 أسعار الذهب اليوم:\n24k: `{prices['24k']}` $\n22k: `{prices['22k']}` $\n21k: `{prices['21k']}` $\n\nاختر العيار المفضل لديك بالأسفل.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data in ["24k","22k","21k"]:
        cursor.execute("UPDATE users SET preferred_karat=? WHERE user_id=?", (query.data, query.from_user.id))
        conn.commit()
        await query.edit_message_text(f"✅ تم تعيين العيار المفضل لديك إلى {query.data.upper()}.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # إرسال تنبيهات كل 5 دقائق
    app.job_queue.run_repeating(send_price_alerts, interval=300, first=0)

    logging.info("🚀 Gold Bot بدأ ويعمل مع تنبيهات حية كل 5 دقائق")
    app.run_polling()
