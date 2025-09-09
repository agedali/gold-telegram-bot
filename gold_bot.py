import os
import requests
import asyncio
from datetime import datetime, time
from telegram import Bot
from telegram.constants import ParseMode

# المتغيرات من GitHub Secrets
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")

bot = Bot(token=TOKEN)

# حساب الأسعار
def get_gold_prices():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    data = response.json()

    if "price" not in data:
        return None

    price_per_ounce = data["price"]  # سعر الأونصة بالدولار
    price_per_gram = price_per_ounce / 31.1035
    price_per_mithqal = price_per_gram * 5  # 1 مثقال = 5 غرام

    # أسعار العيارات (نسبة نقاء الذهب)
    karats = {
        "عيار 24": 1.0,
        "عيار 22": 22 / 24,
        "عيار 21": 21 / 24,
        "عيار 18": 18 / 24,
    }

    prices = {}
    for karat, purity in karats.items():
        gram_price = price_per_gram * purity
        mithqal_price = price_per_mithqal * purity
        prices[karat] = (round(gram_price, 2), round(mithqal_price, 2))

    return {"karats": prices, "ounce": round(price_per_ounce, 2)}

# صياغة الرسالة
def format_message(opening=False, closing=False):
    prices_data = get_gold_prices()
    if not prices_data:
        return "❌ خطأ في جلب أسعار الذهب."

    prices = prices_data["karats"]
    ounce_price = prices_data["ounce"]

    today = datetime.now().strftime("%Y-%m-%d")
    msg = f"📅 {today}\n\n"

    if opening:
        msg += "✅ تم فتح بورصة العراق\n\n"
    elif closing:
        msg += "❌ تم إغلاق بورصة العراق\n\n"

    msg += f"💰 أسعار الذهب:\n• الأونصة: {ounce_price}$\n\n"
    for karat, (gram, mithqal) in prices.items():
        msg += f"{karat}:\n- للغرام: {gram}$\n- للمثقال: {mithqal}$\n\n"

    return msg

# إرسال الرسالة
async def send_prices(opening=False, closing=False):
    msg = format_message(opening, closing)
    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.HTML)

# الجدولة اليومية
async def scheduler():
    while True:
        now = datetime.now().time()

        if now.hour == 10 and now.minute == 0:
            await send_prices(opening=True)
            await asyncio.sleep(60)

        elif now.hour == 17 and now.minute == 0:
            await send_prices(closing=True)
            await asyncio.sleep(60)

        await asyncio.sleep(30)

# تشغيل البوت
async def main():
    await scheduler()

if __name__ == "__main__":
    asyncio.run(main())
