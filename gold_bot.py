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
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # @channelusername أو -100xxxxxxxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")
AFFILIATE_LINK = os.getenv("AFFILIATE_LINK", "https://your-affiliate-link.com")  # رابط الشركاء

# إعداد قاعدة البيانات البسيطة
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

        mithqal_24k = gram_24k * 5
        mithqal_22k = gram_22k * 5
        mithqal_21k = gram_21k * 5

        return {
            "24k": {"gram": gram_24k, "mithqal": mithqal_24k},
            "22k": {"gram": gram_22k, "mithqal": mithqal_22k},
            "21k": {"gram": gram_21k, "mithqal": mithqal_21k},
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None


def format_message(prices: dict):
    """تنسيق الرسالة بشكل احترافي"""
    return (
        "💰 **أسعار الذهب اليوم** 💰\n\n"
        f"🔹 **عيار 24**:\n   - الغرام: `{prices['24k']['gram']:.2f}` $\n   - المثقال: `{prices['24k']['mithqal']:.2f}` $\n\n"
        f"🔹 **عيار 22**:\n   - الغرام: `{prices['22k']['gram']:.2f}` $\n   - المثقال: `{prices['22k']['mithqal']:.2f}` $\n\n"
        f"🔹 **عيار 21**:\n   - الغرام: `{prices['21k']['gram']:.2f}` $\n   - المثقال: `{prices['21k']['mithqal']:.2f}` $\n\n"
        f"💎 للاستفادة من الميزات المميزة و التنبيهات اللحظية، اشترك هنا: [اشتراك مميز]({AFFILIATE_LINK})"
    )


async def send_gold_prices(context: ContextTypes.DEFAULT_TYPE):
    """إرسال الأسعار لكل المستخدمين (مجاني/مدفوع)"""
    prices = fetch_gold_prices()
    if not prices:
        return

    cursor.execute("SELECT user_id, subscription, preferred_karat, preferred_gram FROM users")
    users = cursor.fetchall()
    for user in users:
        user_id, subscription, karat, preferred_gram = user
        if subscription == "premium" and preferred_gram > 0:
            current_price = prices[karat]["gram"]
            # إرسال إشعار فقط إذا تغير السعر أكثر من 1%
            if abs(current_price - preferred_gram)/preferred_gram >= 0.01:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🔔 **تنبيه سعر الذهب {karat.upper()}** 🔔\nالسعر الحالي: `{current_price:.2f}` $\nالاشتراك المميز يتيح لك متابعة التنبيهات اللحظية.",
                    parse_mode="Markdown"
                )
                # تحديث السعر المفضل للمستخدم
                cursor.execute("UPDATE users SET preferred_gram=? WHERE user_id=?", (current_price, user_id))
                conn.commit()


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /price لتحديث فوري مع أزرار"""
    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="24k"),
         InlineKeyboardButton("عيار 22", callback_data="22k"),
         InlineKeyboardButton("عيار 21", callback_data="21k")],
        [InlineKeyboardButton("اشتراك مميز", url=AFFILIATE_LINK)],
        [InlineKeyboardButton("أفضل العروض", url=AFFILIATE_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # إضافة المستخدم تلقائيًا إذا لم يكن موجود
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()

    await update.message.reply_text("اختر العيار لعرض السعر:", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغط الأزرار"""
    query = update.callback_query
    await query.answer()

    prices = fetch_gold_prices()
    if not prices:
        await query.edit_message_text("⚠️ تعذر جلب الأسعار حالياً.")
        return

    choice = query.data
    selected = prices[choice]

    # تحديث السعر المفضل للمستخدم إذا كان مشترك مميز
    user_id = query.from_user.id
    cursor.execute("SELECT subscription FROM users WHERE user_id=?", (user_id,))
    subscription = cursor.fetchone()
    if subscription and subscription[0] == "premium":
        cursor.execute("UPDATE users SET preferred_gram=?, preferred_karat=? WHERE user_id=?",
                       (selected["gram"], choice, user_id))
        conn.commit()

    message = (
        f"💰 **سعر الذهب - {choice.upper()}** 💰\n\n"
        f"🔹 الغرام: `{selected['gram']:.2f}` $\n"
        f"🔹 المثقال: `{selected['mithqal']:.2f}` $\n\n"
        f"💎 للاستفادة من الميزات المميزة و التنبيهات اللحظية، اشترك هنا: [اشتراك مميز]({AFFILIATE_LINK})"
    )

    await query.edit_message_text(message, parse_mode="Markdown")


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # إرسال تحديث تلقائي كل ساعة
    app.job_queue.run_repeating(send_gold_prices, interval=3600, first=0)

    logging.info("🚀 Gold Bot بدأ ويعمل مع تحديث تلقائي كل ساعة وأمر /price")
    app.run_polling()
