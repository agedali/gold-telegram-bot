import logging
import os
import requests
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

# إعداد اللوج
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# مفاتيح البيئة
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # @channelusername أو -100xxxxxxxxx
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")  # Provider Token للنجوم
OKX_WALLET = os.getenv("OKX_WALLET", "TQEFoYompvJzbpaWLp8HWXBsV1aHwZ94n8")  # محفظة USDT TRC20

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
    preferred_karat TEXT DEFAULT '24k',
    last_price_24k REAL DEFAULT 0,
    last_price_22k REAL DEFAULT 0,
    last_price_21k REAL DEFAULT 0
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
            "24k": {"gram": gram_24k, "mithqal": gram_24k*5},
            "22k": {"gram": gram_22k, "mithqal": gram_22k*5},
            "21k": {"gram": gram_21k, "mithqal": gram_21k*5},
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None


def format_message(prices: dict, last_prices: dict = None):
    """تنسيق الرسالة مع ألوان ارتفاع/انخفاض السعر"""
    message = "💰 **أسعار الذهب اليوم** 💰\n\n"
    for karat in ["24k","22k","21k"]:
        current = prices[karat]["gram"]
        last = last_prices.get(karat, 0) if last_prices else 0
        color = "🟢" if current >= last else "🔴"
        message += f"{color} **عيار {karat[:-1]}**\n- الغرام: `{current:.2f}` $\n- المثقال: `{prices[karat]['mithqal']:.2f}` $\n\n"
    message += "💎 الميزات المميزة (الآن مجانية لتجربة):\n"
    message += "- تنبيهات لحظية للسعر\n- اختيار العيار المفضل\n- عرض الرسوم البيانية\n\n"
    message += "اختر طريقة الاشتراك أدناه."
    return message


async def send_gold_prices(context: ContextTypes.DEFAULT_TYPE):
    """إرسال الأسعار لكل المستخدمين"""
    prices = fetch_gold_prices()
    if not prices:
        return

    cursor.execute("SELECT user_id, last_price_24k, last_price_22k, last_price_21k FROM users")
    users = cursor.fetchall()
    for user in users:
        user_id, last_24, last_22, last_21 = user
        last_prices = {"24k": last_24, "22k": last_22, "21k": last_21}

        for karat in ["24k","22k","21k"]:
            current_price = prices[karat]["gram"]
            if abs(current_price - last_prices[karat])/max(last_prices[karat],1) >= 0.01:
                color = "🟢" if current_price >= last_prices[karat] else "🔴"
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"{color} **تنبيه سعر الذهب {karat.upper()}**\nالسعر الحالي: `{current_price:.2f}` $",
                    parse_mode="Markdown"
                )
                # تحديث السعر الأخير
                cursor.execute(f"UPDATE users SET last_price_{karat}=? WHERE user_id=?", (current_price, user_id))
                conn.commit()


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /price مع أزرار"""
    user_id = update.message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
    conn.commit()

    # جلب آخر الأسعار
    cursor.execute("SELECT last_price_24k, last_price_22k, last_price_21k FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    last_prices = {"24k": row[0], "22k": row[1], "21k": row[2]} if row else None

    keyboard = [
        [InlineKeyboardButton("عيار 24", callback_data="24k"),
         InlineKeyboardButton("عيار 22", callback_data="22k"),
         InlineKeyboardButton("عيار 21", callback_data="21k")],
        [InlineKeyboardButton("اشتراك بالنجوم ⭐", callback_data="subscribe_stars")],
        [InlineKeyboardButton("اشتراك بالـ USDT 💰", callback_data="subscribe_crypto")],
    ]

    # أزرار الشركاء
    for link in AFFILIATE_LINKS:
        keyboard.append([InlineKeyboardButton(link["text"], url=link["url"])])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(format_message(fetch_gold_prices(), last_prices), reply_markup=reply_markup, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغط الأزرار"""
    query = update.callback_query
    await query.answer()

    if query.data in ["24k","22k","21k"]:
        prices = fetch_gold_prices()
        if not prices:
            await query.edit_message_text("⚠️ تعذر جلب الأسعار حالياً.")
            return
        selected = prices[query.data]
        user_id = query.from_user.id

        # جلب السعر السابق للمقارنة
        cursor.execute(f"SELECT last_price_{query.data} FROM users WHERE user_id=?", (user_id,))
        last_price = cursor.fetchone()[0]
        color = "🟢" if selected["gram"] >= last_price else "🔴"

        # تحديث السعر الأخير
        cursor.execute(f"UPDATE users SET last_price_{query.data}=? WHERE user_id=?", (selected["gram"], user_id))
        conn.commit()

        message = f"{color} **سعر الذهب - {query.data.upper()}**\n- الغرام: `{selected['gram']:.2f}` $\n- المثقال: `{selected['mithqal']:.2f}` $"
        await query.edit_message_text(message, parse_mode="Markdown")

    elif query.data == "subscribe_stars":
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title="اشتراك Premium",
            description="تنبيهات لحظية لأسعار الذهب ومزايا إضافية",
            payload="premium_stars",
            provider_token=PAYMENT_TOKEN,
            currency="USD",
            prices=[LabeledPrice("اشتراك شهري", 500)]  # 5$
        )
    elif query.data == "subscribe_crypto":
        await query.edit_message_text(
            f"💰 لدفع الاشتراك بالـ USDT:\n"
            f"- المبلغ المطلوب: 5 USDT\n"
            f"- الشبكة: TRC20\n"
            f"- عنوان المحفظة: `{OKX_WALLET}`\n\n"
            "✅ بعد الدفع، سيتم التفعيل تلقائيًا عند التحقق من المحفظة."
        )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute("UPDATE users SET subscription='premium' WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text("🎉 تم تفعيل اشتراكك المميز بنجاح!")


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # أوامر وأزرار
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # إرسال تحديث تلقائي كل ساعة
    app.job_queue.run_repeating(send_gold_prices, interval=3600, first=0)

    logging.info("🚀 Gold Bot بدأ ويعمل مع تحديث تلقائي كل ساعة وأمر /price")
    app.run_polling()
