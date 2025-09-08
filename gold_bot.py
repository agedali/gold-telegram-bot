import os
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes
)
from datetime import datetime, time
import asyncio
import nest_asyncio

nest_asyncio.apply()

# ===== متغيرات البيئة =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

# ===== جلب أسعار الذهب من GOLDAPI =====
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {
            "gram_24": data["price_gram_24k"],
            "gram_22": data["price_gram_22k"],
            "gram_21": data["price_gram_21k"],
            "ounce": data["price"]
        }
    except Exception as e:
        print("❌ خطأ في استدعاء أسعار الذهب:", e)
        return None

# ===== جلب أسعار صرف الدولار واليورو مقابل الدينار العراقي =====
def get_fx_rates():
    try:
        url = "https://qamaralfajr.com/production/exchange_rates.php"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        rates = {}
        table = soup.find("table")
        if not table:
            return None
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 3:
                currency = cols[0].text.strip()
                buy = cols[1].text.strip()
                sell = cols[2].text.strip()
                if currency in ["USD", "EUR"]:
                    rates[currency] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        print("❌ خطأ في جلب أسعار الصرف:", e)
        return None

# ===== صياغة الرسالة =====
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

# ===== إرسال الأسعار للقناة =====
async def send_prices_job(context: ContextTypes.DEFAULT_TYPE):
    msg = format_message()
    keyboard = [
        [InlineKeyboardButton("📸 تابعنا على إنستغرام", url="https://www.instagram.com/aged_ali40?igsh=Nm42ZXVybTlia3Z0&utm_source=qr")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# ===== جدولة الرسائل =====
async def schedule_prices(app):
    for hour in range(10, 18):  # من 10 صباحًا حتى 5 مساءً
        app.job_queue.run_daily(send_prices_job, time=time(hour, 0, 0), days=(0,1,2,3,4,5,6))

# ===== تشغيل البوت =====
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # إرسال الأسعار أول مرة فور التشغيل
    app.job_queue.run_once(send_prices_job, when=0)

    # جدولة الأسعار
    await schedule_prices(app)

    # تشغيل البوت
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
