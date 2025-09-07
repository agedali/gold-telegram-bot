import os
import re
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, ContextTypes,
    ConversationHandler, MessageHandler, CommandHandler, filters
)

# ========== إعداد اللوج ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ========== متغيرات البيئة ==========
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")  # مفتاح GoldAPI

if not BOT_TOKEN or not CHAT_ID:
    logging.warning("⚠️ تأكد من ضبط TELEGRAM_TOKEN و TELEGRAM_CHAT_ID في Secrets/Environment.")

# ========== خرائط أيام بالعربي ==========
DAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# ========== حالات المحادثة لزر حساب الأرباح ==========
PROFIT_GRAMS, PROFIT_TOTAL = range(2)

# ========== أدوات مساعدة ==========
def _to_float(s: str) -> float:
    """تحويل نص برقم مع فواصل/رموز إلى float."""
    if s is None:
        return 0.0
    # إزالة أي شيء غير أرقام ونقاط وفواصل
    s = re.sub(r"[^\d\.,]", "", str(s))
    # إن وُجدت نقطة وفاصلة: اعتبر الفاصلة فاصلة آلاف
    if "," in s and "." in s:
        s = s.replace(",", "")
    else:
        # إذا الفاصلة فقط غالباً آلاف
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0

# ========== جلب أسعار الصرف من qamaralfajr ==========
def get_fx_rates():
    """
    يحاول قراءة JSON من:
      https://qamaralfajr.com/production/exchange_rates.php
    وإن فشل، يحاول تحليل HTML (جدول).
    يعيد dict: {"USD": {"buy": ..., "sell": ...}, "EUR": {...}}
    """
    url = "https://qamaralfajr.com/production/exchange_rates.php"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Referer": "https://qamaralfajr.com/"
    }
    try:
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        rates = {}

        # جرّب JSON أولاً
        try:
            data = r.json()
        except ValueError:
            data = None

        def pick_buy_sell(d: dict):
            """يحاول إيجاد حقول الشراء/البيع بأسماء مختلفة."""
            if not isinstance(d, dict):
                return None
            lowered = {str(k).lower(): d[k] for k in d}
            # احتمالات المفاتيح
            buy_key = next((k for k in lowered if "buy" in k or "شراء" in k), None)
            sell_key = next((k for k in lowered if "sell" in k or "بيع" in k), None)
            if buy_key and sell_key:
                return _to_float(lowered[buy_key]), _to_float(lowered[sell_key])
            # fallback إذا مفاتيح مختلفة
            nums = [v for v in lowered.values() if isinstance(v, (int, float, str))]
            nums = [_to_float(v) for v in nums if _to_float(v) > 0]
            if len(nums) >= 2:
                return nums[0], nums[1]
            return None

        if data is not None:
            # قد يكون List أو Dict يحوي List
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                # جرّب أكثر من مفتاح شائع
                for key in ("data", "rates", "result"):
                    if key in data and isinstance(data[key], list):
                        items = data[key]
                        break
                if not items:
                    # إذا dict مسطّح
                    items = [data]

            for item in items:
                if not isinstance(item, dict):
                    continue
                text_all = " ".join([str(v) for v in item.values()]).lower()
                is_usd = ("usd" in text_all) or ("دولار" in text_all)
                is_eur = ("eur" in text_all) or ("يورو" in text_all)
                bs = pick_buy_sell(item)
                if bs:
                    b, s = bs
                    if is_usd:
                        rates["USD"] = {"buy": b, "sell": s}
                    if is_eur:
                        rates["EUR"] = {"buy": b, "sell": s}

        # لو ما استخرجنا من JSON، جرّب HTML
        if not rates:
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table")
            if table:
                for row in table.find_all("tr"):
                    cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                    if len(cols) >= 3:
                        name = cols[0]
                        buy = _to_float(cols[1])
                        sell = _to_float(cols[2])
                        name_low = name.lower()
                        if "usd" in name_low or "دولار" in name_low:
                            rates["USD"] = {"buy": buy, "sell": sell}
                        if "eur" in name_low or "يورو" in name_low:
                            rates["EUR"] = {"buy": buy, "sell": sell}

        return rates
    except Exception as e:
        logging.error(f"❌ Error fetching FX rates: {e}")
        return {}

# ========== جلب أسعار الذهب من GoldAPI ==========
def get_gold_prices(usd_iqd_rate: float):
    """
    يستخدم GoldAPI:
      - price_gram_24k للغرام 24
      - price (أونصة تروي بالدولار)
    يعيد أسعار بالدولار وبالدينار (حسب usd_iqd_rate = سعر بيع الدولار بالدينار).
    """
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY or "", "Content-Type": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        gram24 = float(data.get("price_gram_24k") or 0)
        ounce_usd = float(data.get("price") or 0)  # أونصة بالدولار

        if gram24 <= 0 or ounce_usd <= 0:
            raise ValueError("Missing or zero gold prices from API.")

        prices = {
            "gram_24_usd": gram24,
            "gram_22_usd": gram24 * 22 / 24,
            "gram_21_usd": gram24 * 21 / 24,
            "ounce_usd": ounce_usd,
        }
        # تحويل إلى دينار
        for k in list(prices.keys()):
            if k.endswith("_usd"):
                prices[k.replace("_usd", "_iqd")] = prices[k] * usd_iqd_rate

        return prices
    except Exception as e:
        logging.error(f"❌ Error fetching gold prices: {e}")
        return None

# ========== تنسيق الرسالة ==========
def build_prices_message():
    # يوم وتاريخ
    now = datetime.now()
    day = DAYS_AR[now.weekday()]
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # أسعار الصرف
    fx = get_fx_rates()
    if not fx or "USD" not in fx:
        return "❌ خطأ في جلب أسعار الصرف."

    usd_sell = fx["USD"]["sell"] or fx["USD"]["buy"] or 0.0  # نستخدم البيع كمرجع تحويل
    prices = get_gold_prices(usd_iqd_rate=usd_sell)
    if not prices:
        return "❌ خطأ في جلب أسعار الذهب."

    msg = []
    msg.append(f"📅 {day} - {time_str}\n")
    msg.append("💰 أسعار الذهب:")
    msg.append(f"• 24k: {prices['gram_24_usd']:.2f} $ | {prices['gram_24_iqd']:.0f} IQD")
    msg.append(f"• 22k: {prices['gram_22_usd']:.2f} $ | {prices['gram_22_iqd']:.0f} IQD")
    msg.append(f"• 21k: {prices['gram_21_usd']:.2f} $ | {prices['gram_21_iqd']:.0f} IQD")
    msg.append(f"• الأونصة: {prices['ounce_usd']:.2f} $ | {prices['ounce_iqd']:.0f} IQD\n")

    msg.append("💱 أسعار العملات مقابل الدينار العراقي:")
    for code in ("USD", "EUR"):
        if code in fx:
            b = fx[code]["buy"]
            s = fx[code]["sell"]
            msg.append(f"• {code}: شراء {b:.0f} | بيع {s:.0f}")

    return "\n".join(msg)

# ========== إرسال الأسعار مع زر ==========
async def send_prices_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        message = build_prices_message()
        keyboard = [[InlineKeyboardButton("📊 حساب الأرباح", callback_data="calc_profit")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=CHAT_ID, text=message, reply_markup=reply_markup)
    except Exception as e:
        logging.error(f"❌ send_prices_job error: {e}")

# ========== محادثة حساب الأرباح ==========
async def profit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # انطلق من الضغط على الزر
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("أدخل عدد الغرامات التي اشتريتها (مثال: 10)")
    return PROFIT_GRAMS

async def profit_get_grams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    g = _to_float(txt)
    if g <= 0:
        await update.message.reply_text("⚠️ رجاءً أدخل رقم صحيح للغرامات.")
        return PROFIT_GRAMS
    context.user_data["grams"] = g
    await update.message.reply_text(f"أرسل المبلغ الإجمالي بالدولار لشراء ({g} غرام):")
    return PROFIT_TOTAL

async def profit_get_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = _to_float(update.message.text.strip())
    grams = context.user_data.get("grams", 0.0)
    if total <= 0 or grams <= 0:
        await update.message.reply_text("⚠️ بيانات غير صالحة. أعد المحاولة من زر حساب الأرباح.")
        return ConversationHandler.END

    buy_price_per_gram = total / grams

    # نستخدم سعر 24k الحالي
    fx = get_fx_rates()
    if not fx or "USD" not in fx:
        await update.message.reply_text("⚠️ تعذّر جلب أسعار الصرف حالياً.")
        return ConversationHandler.END

    usd_sell = fx["USD"]["sell"] or fx["USD"]["buy"] or 0.0
    gold = get_gold_prices(usd_sell)
    if not gold:
        await update.message.reply_text("⚠️ تعذّر جلب أسعار الذهب حالياً.")
        return ConversationHandler.END

    current_gram_24 = gold["gram_24_usd"]
    profit = (current_gram_24 - buy_price_per_gram) * grams
    emoji = "🟢 ربح" if profit >= 0 else "🔴 خسارة"

    await update.message.reply_text(
        f"{emoji}\n"
        f"• الكمية: {grams:.3f} غرام\n"
        f"• سعر الشراء/غرام: {buy_price_per_gram:.2f} $\n"
        f"• السعر الحالي/غرام (24k): {current_gram_24:.2f} $\n"
        f"• الصافي: {profit:.2f} $"
    )
    # تنظيف
    context.user_data.pop("grams", None)
    return ConversationHandler.END

async def profit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("grams", None)
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# ========== الدالة الرئيسية ==========
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # محادثة زر حساب الأرباح
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(profit_entry, pattern="^calc_profit$")],
        states={
            PROFIT_GRAMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, profit_get_grams)],
            PROFIT_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, profit_get_total)],
        },
        fallbacks=[CommandHandler("cancel", profit_cancel)],
        per_message=False,  # تحذير افتراضي؛ سلوك مناسب لحالتنا
    )
    app.add_handler(conv)

    # أرسل الأسعار مرة واحدة فور تشغيل البوت (عند بدء الـ JobQueue)
    app.job_queue.run_once(send_prices_job, when=0)

    logging.info("🚀 Gold Bot جاهز للعمل")
    # مهم: لا تستخدم await هنا. هذا استدعاء متزامن يمنع مشاكل الحدث.
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
