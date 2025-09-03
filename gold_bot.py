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
    filters,
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
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
    preferred_karat TEXT DEFAULT '24k',
    last_price REAL DEFAULT 0
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
cursor.execute("""
CREATE TABLE IF NOT EXISTS purchase_price (
    user_id INTEGER,
    karat TEXT,
    purchase_price REAL,
    PRIMARY KEY(user_id, karat)
)
""")
conn.commit()

# ترجمة أيام الأسبوع للعربي
DAYS_AR = {
    "Monday": "الاثنين",
    "Tuesday": "الثلاثاء",
    "Wednesday": "الأربعاء",
    "Thursday": "الخميس",
    "Friday": "الجمعة",
    "Saturday": "السبت",
    "Sunday": "الأحد"
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
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

def format_main_message(prices: dict):
    now = datetime.now()
    day_name = DAYS_AR[now.strftime("%A")]
    date_str = now.strftime("%d/%m/%Y")
    message = f"💰 **أسعار الذهب اليوم - {day_name}, {date_str}** 💰\n\n"
    for karat in ["24k", "22k", "21k"]:
        current = prices[karat]["gram"]
        color = "🟢" if current >= 0 else "🔴"
        message += f"{color} **عيار {karat[:-1]}**\n- الغرام: `{current:.2f}` $\n- المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    message += "💎 اختر العيار للعرض أو أحد الروابط أدناه.\n"
    message += "💵 لإضافة سعر الشراء الخاص بك، استخدم /buy"
    return message

async def send_gold_prices(context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    if not prices:
        return

    now = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT user_id, preferred_karat, last_price FROM users")
    users = cursor.fetchall()

    for user in users:
        user_id, karat, last_price = user
        current_price = prices[karat]["gram"]

        # إرسال إشعار عند تغير السعر أكثر من 1%
        if last_price == 0 or abs(current_price - last_price)/last_price >= 0.01:
            color = "🟢" if current_price >= last_price else "🔴"
            await context.bot.send_message(
                chat_id=user_id,
                text=f"{color} **تنبيه سعر الذهب {karat.upper()}**\nالسعر الحالي: `{current_price:.2f}` $",
                parse_mode="Markdown"
            )
            cursor.execute("UPDATE users SET last_price=? WHERE user_id=?", (current_price, user_id))
            conn.commit()

        # حفظ السعر في جدول price_history
        cursor.execute("""
            INSERT OR REPLACE INTO price_history(user_id, karat, price, date)
            VALUES (?, ?, ?, ?)
        """, (user_id, karat, current_price, now))
        conn.commit()

        # تنبيه الربح/الخسارة للمستخدمين الذين أضافوا سعر شراء
        cursor.execute("SELECT purchase_price FROM purchase_price WHERE user_id=? AND karat=?", (user_id, karat))
        row = cursor.fetchone()
        if row:
            purchase_price = row[0]
            diff = current_price - purchase_price
            status = "💰 ربح" if diff > 0 else "📉 خسارة"
            await context.bot.send_message(
                chat_id=user_id,
                text=f"{status} لعيار {karat.upper()}: `{diff:.2f}` $ (سعر الشراء `{purchase_price:.2f}` $, السعر الحالي `{current_price:.2f}` $)",
                parse_mode="Markdown"
            )

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()

    prices = fetch_gold_prices()
    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="24k"),
         InlineKeyboardButton("عيار 22", callback_data="22k"),
         InlineKeyboardButton("عيار 21", callback_data="21k")],
    ]
    for link in AFFILIATE_LINKS:
        keyboard.append([InlineKeyboardButton(link["text"], url=link["url"])])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(format_main_message(prices), reply_markup=reply_markup, parse_mode="Markdown")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب إدخال سعر الشراء"""
    await update.message.reply_text(
        "💵 أرسل سعر شراء الذهب وعياره بصيغة:\n"
        "`عيار السعر`\n"
        "مثال: `24 1800` يعني عيار 24 بسعر 1800$",
        parse_mode="Markdown"
    )
    return

async def handle_buy_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        karat, price = text.split()
        karat = karat + "k" if karat in ["21", "22", "24"] else None
        price = float(price)
        if not karat:
            await update.message.reply_text("⚠️ العيار غير صحيح. استخدم 21 أو 22 أو 24")
            return
        cursor.execute("INSERT OR REPLACE INTO purchase_price(user_id, karat, purchase_price) VALUES (?, ?, ?)",
                       (update.message.from_user.id, karat, price))
        conn.commit()
        await update.message.reply_text(f"✅ تم حفظ سعر شراء الذهب عيار {karat} بـ {price} $ بنجاح")
    except Exception as e:
        await update.message.reply_text("⚠️ صيغة الرسالة غير صحيحة. استخدم مثال: `24 1800`")
        logging.error(e)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute("SELECT karat, price, date FROM price_history WHERE user_id=? ORDER BY date DESC", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("⚠️ لا يوجد سجل أسعار بعد.")
        return

    message = "📊 **سجل أسعار الذهب** 📊\n\n"
    last_prices = {}
    for karat, price, date in rows:
        prev = last_prices.get(karat, price)
        color = "🟢" if price >= prev else "🔴"
        message += f"{color} {karat.upper()} - {date}: `{price:.2f}` $\n"
        last_prices[karat] = price

    await update.message.reply_text(message, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prices = fetch_gold_prices()
    if query.data in ["24k", "22k", "21k"]:
        cursor.execute("UPDATE users SET preferred_karat=? WHERE user_id=?", (query.data, query.from_user.id))
        conn.commit()
        selected = prices[query.data]
