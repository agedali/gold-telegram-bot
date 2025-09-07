import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, ContextTypes
)
from datetime import datetime, time
import asyncio
import nest_asyncio

nest_asyncio.apply()

# --- متغيرات البيئة ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# --- دالة سحب أسعار الذهب ---
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # استخدم المفتاح الصحيح من GOLDAPI
        gram24 = data.get("price_gram_24k") or data.get("price")  # تأكد من المفتاح الصحيح
        if not gram24:
            print("❌ خطأ في استدعاء أسعار الذهب")
            return None

        return {
            "gram_24": gram24,
            "gram_22": gram24 * 22 / 24,
            "gram_21": gram24 * 21 / 24,
            "ounce": data.get("price_ounce") or 0
        }
    except Exception as e:
        print("❌ Error fetching gold prices:", e)
        return None

# --- دالة سحب سعر الدولار واليورو مقابل الدينار العراقي ---
def get_fx_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        rates = {}
        table = soup.find("table")
        if not table:
            print("❌ لم أجد جدول الأسعار في الصفحة")
            return {}

        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 3:
                currency = cols[0].text.strip()
                buy = cols[1].text.strip().replace(",", "")
                sell = cols[2].text.strip().replace(",", "")
                if currency in ["USD", "EUR"]:
                    rates[currency] = {"buy": buy, "sell": sell}
        if not rates:
            print("❌ لم أستطع العثور على أسعار الدولار واليورو")
        return rates
    except Exception as e:
        print("❌ Error fetching FX rates:", e)
        return {}

# --- صياغة الرسالة ---
def format_message():
    gold = get_gold_prices()
    fx = get_fx_rates()
    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    if gold:
        msg += "💰 أسعار الذهب بالدولار الأمريكي:\n"
        msg += f"• عيار 24: {gold['gram_24']:.2f} $\n"
        msg += f"• عيار 22: {gold['gram_22']:.2f} $\n"
        msg += f"• عيار 21: {gold['gram_21']:.2f} $\n"
        msg += f"• الأونصة: {gold['ounce']:.2f} $\n\n"
    else:
        msg += "❌ خطأ في جلب أسعار الذهب.\n\n"

    if fx:
        msg += "💱 أسعار العملات مقابل الدينار العراقي:\n"
        for curr in fx:
            msg += f"• {curr} شراء: {fx[curr]['buy']} | بيع: {fx[curr]['sell']}\n"
    else:
        msg += "❌ خطأ في جلب أسعار الصرف.\n"

    return msg

# --- إرسال الأسعار مع زر حساب الأرباح ---
async def send_prices(context: ContextTypes.DEFAULT_TYPE):
    msg = format_message()
    keyboard = [
        [InlineKeyboardButton("حساب الأرباح", callback_data="calculate_profit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# --- التعامل مع زر حساب الأرباح ---
async def button_handler(update: "telegram.Update", context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="💰 الرجاء إرسال بيانات الغرامات والمبلغ الإجمالي عبر المحادثة مع البوت لاحقًا")

# --- جدولة إرسال الأسعار كل ساعة من 10 صباحًا حتى 6 مساءً ---
async def schedule_prices(app):
    for hour in range(10, 19):
        app.job_queue.run_daily(send_prices, time=time(hour, 0, 0))

# --- تشغيل البوت ---
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CallbackQueryHandler(button_handler, pattern="calculate_profit"))

    # إرسال الأسعار أول مرة عند التشغيل
    await send_prices(app)

    # جدولة الإرسال
    await schedule_prices(app)

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
