import logging
import os
import requests
import sqlite3
from datetime import datetime
from io import BytesIO
import plotly.graph_objects as go
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
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
    preferred_karats TEXT DEFAULT '24k,22k,21k',
    alert_percentage REAL DEFAULT 1.0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS price_history (
    user_id INTEGER,
    karat TEXT,
    price REAL,
    date TEXT,
    PRIMARY KEY(user_id, karat, date)
)
""")
conn.commit()


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


def format_message(prices: dict):
    now = datetime.now()
    day_name = now.strftime("%A")
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day_name}, {date_str}** 💰\n\n"
    for karat in ["24k", "22k", "21k"]:
        current = prices[karat]["gram"]
        color = "🟢" if current >= 0 else "🔴"
        message += f"{color} **عيار {karat[:-1]}**\n- الغرام: `{current:.2f}` $\n- المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    message += "💎 الميزات المتاحة:\n- تنبيهات لحظية للسعر\n- متابعة أكثر من عيار\n- سجل الأسعار محفوظ للرسم البياني\n"
    message += "اختر العيار للعرض أو أحد الروابط أدناه."
    return message


async def send_gold_prices(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    if not prices:
        return

    cursor.execute("SELECT user_id, preferred_karats, alert_percentage FROM users")
    users = cursor.fetchall()
    now = datetime.now().strftime("%Y-%m-%d")
    
    for user in users:
        user_id, karats, alert_percentage = user
        karat_list = karats.split(",")
        for karat in karat_list:
            current_price = prices[karat]["gram"]

            # حفظ السعر في جدول price_history
            cursor.execute("""
                INSERT OR REPLACE INTO price_history(user_id, karat, price, date)
                VALUES (?, ?, ?, ?)
            """, (user_id, karat, current_price, now))
            conn.commit()

            # تنبيه لحظي
            color = "🟢" if current_price >= 0 else "🔴"
            await context.bot.send_message(
                chat_id=user_id,
                text=f"{color} **تنبيه سعر الذهب {karat.upper()}**\nالسعر الحالي: `{current_price:.2f}` $",
                parse_mode="Markdown"
            )


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()

    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="24k"),
         InlineKeyboardButton("عيار 22", callback_data="22k"),
         InlineKeyboardButton("عيار 21", callback_data="21k")],
        [InlineKeyboardButton("عرض الرسم البياني 📈", callback_data="chart")],
    ]

    # أزرار الشركاء
    for link in AFFILIATE_LINKS:
        keyboard.append([InlineKeyboardButton(link["text"], url=link["url"])])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(format_message(fetch_gold_prices()), reply_markup=reply_markup, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data in ["24k", "22k", "21k"]:
        prices = fetch_gold_prices()
        if not prices:
            await query.edit_message_text("⚠️ تعذر جلب الأسعار حالياً.")
            return
        selected = prices[query.data]
        message = f"💰 **سعر الذهب - {query.data.upper()}**\n- الغرام: `{selected['gram']:.2f}` $\n- المثقال: `{selected['mithqal']:.2f}` $"
        await query.edit_message_text(message, parse_mode="Markdown")

    elif query.data == "chart":
        user_id = query.from_user.id
        # جلب كل البيانات لكل العيارات
        cursor.execute("SELECT karat, date, price FROM price_history WHERE user_id=? ORDER BY date ASC", (user_id,))
        data = cursor.fetchall()
        if not data:
            await query.edit_message_text("⚠️ لا توجد بيانات للرسم البياني بعد.")
            return

        # تجهيز البيانات للرسم البياني
        chart_data = {}
        for karat, date, price in data:
            chart_data.setdefault(karat, []).append((date, price))

        fig = go.Figure()
        for karat, values in chart_data.items():
            dates, prices_list = zip(*values)
            fig.add_trace(go.Scatter(x=dates, y=prices_list, mode='lines+markers', name=f"{karat.upper()}"))

        fig.update_layout(
            title="📈 تاريخ أسعار الذهب",
            xaxis_title="التاريخ",
            yaxis_title="السعر ($)",
            template="plotly_dark"
        )

        img_bytes = fig.to_image(format="png")
        bio = BytesIO(img_bytes)
        bio.name = "chart.png"
        bio.seek(0)

        await context.bot.send_photo(chat_id=user_id, photo=bio)


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # إرسال تحديث تلقائي كل ساعة
    app.job_queue.run_repeating(send_gold_prices, interval=3600, first=0)

    logging.info("🚀 Gold Bot بدأ ويعمل مع تحديث تلقائي كل ساعة وأمر /price")
    app.run_polling()
