import logging
import os
import requests
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ================== إعداد اللوج ==================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ================== مفاتيح البيئة ==================
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# ================== قاعدة البيانات ==================
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS purchase_price (
    user_id INTEGER,
    karat TEXT,
    purchase_price REAL,  -- سعر الوحدة (لكل غرام أو لكل مثقال)
    unit TEXT,            -- gram أو mithqal
    amount REAL,          -- الكمية التي اشتراها المستخدم
    PRIMARY KEY(user_id, karat, unit)
)
""")
conn.commit()

# ================== ثوابت المحادثة ==================
SELECT_KARAT, SELECT_UNIT, ENTER_AMOUNT, ENTER_PRICE = range(4)

# ================== أسماء الأيام بالعربية ==================
ARABIC_DAYS = {
    0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء",
    3: "الخميس", 4: "الجمعة", 5: "السبت", 6: "الأحد"
}

# ================== أدوات مساعدة ==================
def baghdad_now():
    return datetime.now(ZoneInfo("Asia/Baghdad"))

def main_keyboard():
    # زر واحد فقط لبدء حساب الأرباح
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("حساب أرباحك من الذهب 💰", callback_data="action:buy")]
    ])

def fetch_gold_prices():
    """جلب أسعار الذهب الحالية بالدولار من GoldAPI"""
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()

        # أسعار الغرام لكل عيار
        g24 = float(data.get("price_gram_24k") or 0)
        g22 = float(data.get("price_gram_22k") or 0)
        g21 = float(data.get("price_gram_21k") or 0)

        if not all([g24, g22, g21]):
            return None

        # المثقال = 5 غرام
        return {
            "24k": {"gram": g24, "mithqal": g24 * 5},
            "22k": {"gram": g22, "mithqal": g22 * 5},
            "21k": {"gram": g21, "mithqal": g21 * 5},
        }
    except Exception as e:
        logging.exception("Failed to fetch gold prices: %s", e)
        return None

def format_prices_message(prices: dict) -> str:
    now = baghdad_now()
    day = ARABIC_DAYS[now.weekday()]
    date = now.strftime("%d/%m/%Y")
    # نستخدم HTML لتفادي مشاكل Markdown
    msg = f"💰 <b>أسعار الذهب اليوم - {day} {date}</b> 💰\n\n"
    for karat in ["24k", "22k", "21k"]:
        human = karat[:-1]  # 24, 22, 21
        gram = prices[karat]["gram"]
        mithqal = prices[karat]["mithqal"]
        msg += (
            f"• <b>عيار {human}</b>\n"
            f"  - الغرام: <code>{gram:.2f}</code> $\n"
            f"  - المثقال: <code>{mithqal:.2f}</code> $\n\n"
        )
    msg += "اضغط الزر بالأسفل لحساب أرباحك بناءً على سعر شرائك 👇"
    return msg

# ================== الأوامر العامة ==================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلًا بك! هذا بوت أسعار الذهب وحساب الأرباح.\n\n"
        "– لعرض الأسعار الحالية: استخدم /price\n"
        "– لحساب أرباحك من الذهب: استخدم /buy أو اضغط الزر بالأسفل.",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = fetch_gold_prices()
    if not prices:
        await update.message.reply_text("⚠️ تعذر جلب أسعار الذهب حاليًا. حاول لاحقًا.")
        return

    await update.message.reply_text(
        format_prices_message(prices),
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

# ================== محادثة حساب الأرباح ==================
async def start_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry: من /buy أو من زر inline action:buy"""
    query = update.callback_query if update.callback_query else None
    text = "اختر العيار الذي قمت بشرائه:"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("24k", callback_data="karat:24k")],
        [InlineKeyboardButton("22k", callback_data="karat:22k")],
        [InlineKeyboardButton("21k", callback_data="karat:21k")],
    ])

    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)

    return SELECT_KARAT

async def select_karat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # التحقق من النمط karat:xx
    data = query.data
    if not data.startswith("karat:"):
        # إذا ضغط زر غير متوقع، نعيد المستخدم للبداية
        await query.edit_message_text("حدث خطأ. لنعد للبداية.", reply_markup=main_keyboard())
        return ConversationHandler.END

    karat = data.split(":", 1)[1]
    context.user_data["karat"] = karat

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("غرام", callback_data="unit:gram")],
        [InlineKeyboardButton("مثقال", callback_data="unit:mithqal")],
    ])
    await query.edit_message_text("اختر الوحدة التي اشتريت بها الذهب:", reply_markup=kb)
    return SELECT_UNIT

async def select_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("unit:"):
        await query.edit_message_text("حدث خطأ. لنعد للبداية.", reply_markup=main_keyboard())
        return ConversationHandler.END

    unit = data.split(":", 1)[1]
    context.user_data["unit"] = unit

    await query.edit_message_text(f"أدخل كمية الذهب بالـ {('غرام' if unit=='gram' else 'مثقال')}:")
    return ENTER_AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip().replace(",", ".")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("⚠️ أدخل قيمة رقمية صحيحة للكمية (أكبر من صفر):")
        return ENTER_AMOUNT

    context.user_data["amount"] = amount
    await update.message.reply_text("أدخل <b>سعر الشراء الإجمالي بالدولار</b> (المبلغ الذي دفعته لهذه الكمية):", parse_mode="HTML")
    return ENTER_PRICE

async def enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip().replace(",", ".")
    try:
        total_price = float(raw)
        if total_price <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("⚠️ أدخل قيمة رقمية صحيحة لسعر الشراء الإجمالي (أكبر من صفر):")
        return ENTER_PRICE

    karat = context.user_data.get("karat")
    unit = context.user_data.get("unit")
    amount = context.user_data.get("amount")

    # سعر الشراء لكل وحدة
    unit_price = total_price / amount

    # حفظ العملية في القاعدة
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO purchase_price(user_id, karat, purchase_price, unit, amount)
            VALUES (?, ?, ?, ?, ?)
        """, (update.message.from_user.id, karat, unit_price, unit, amount))
        conn.commit()
    except Exception as e:
        logging.exception("DB error: %s", e)

    # جلب السعر الحالي وحساب الربح/الخسارة
    prices = fetch_gold_prices()
    if not prices:
        await update.message.reply_text("⚠️ تم حفظ بياناتك، لكن تعذر جلب السعر الحالي الآن. حاول لاحقًا.")
        return ConversationHandler.END

    current_unit_price = prices[karat][unit]
    profit_loss = (current_unit_price - unit_price) * amount
    status = "ربح" if profit_loss >= 0 else "خسارة"
    arrow = "🟢" if profit_loss >= 0 else "🔴"

    msg = (
        f"✅ <b>تم حفظ عملية الشراء</b>\n"
        f"• العيار: <b>{karat}</b>\n"
        f"• الوحدة: <b>{'غرام' if unit=='gram' else 'مثقال'}</b>\n"
        f"• الكمية: <b>{amount}</b>\n"
        f"• سعر الشراء لكل وحدة: <code>{unit_price:.2f}</code> $\n\n"
        f"💹 <b>السعر الحالي</b> لكل وحدة: <code>{current_unit_price:.2f}</code> $\n"
        f"{arrow} <b>{status}</b>: <code>{abs(profit_loss):.2f}</code> $"
    )

    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard())
    return ConversationHandler.END

# ================== نقطة دخول البوت ==================
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("❌ TELEGRAM_TOKEN غير موجود في المتغيرات البيئية.")
    if not GOLDAPI_KEY:
        logging.warning("⚠️ GOLDAPI_KEY غير موجود. لن تعمل الأسعار والربح/الخسارة.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("price", price_command))
    # نفس محادثة الأرباح عبر /buy أو الزر
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("buy", start_buy),
            CallbackQueryHandler(start_buy, pattern=r"^action:buy$")
        ],
        states={
            SELECT_KARAT: [CallbackQueryHandler(select_karat, pattern=r"^karat:(24k|22k|21k)$")],
            SELECT_UNIT: [CallbackQueryHandler(select_unit, pattern=r"^unit:(gram|mithqal)$")],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            ENTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_price)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(conv)

    logging.info("🚀 Gold Bot يعمل الآن")
    app.run_polling()
