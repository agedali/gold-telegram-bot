import os
import requests
import asyncio
from datetime import datetime
from telegram import Bot
from telegram.constants import ParseMode

# المتغيرات من GitHub Secrets
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")   # القناة
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")  # حساب الأدمن (من Secrets)

bot = Bot(token=TOKEN)

# جلب الأسعار من GoldAPI فقط
def get_gold_from_goldapi():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            error_msg = f"❌ خطأ GoldAPI: {response.status_code}\nالرد: {response.text}"
            asyncio.create_task(send_error(error_msg))
            return None

        data = response.json()
        if "price" not in data:
            error_msg = f"❌ الرد لا يحتوي على السعر:\n{data}"
            asyncio.create_task(send_error(error_msg))
            return None

        return data["price"]

    except Exception as e:
        error_msg = f"❌ استثناء أثناء جلب السعر:\n{str(e)}"
        asyncio.create_task(send_error(error_msg))
        return None

# حساب الأسعار
def get_gold_prices():
    price_per_ounce = get_gold_from_goldapi()
    if not price_per_ounce:
        return None

    price_per_gram = price_per_ounce / 31.1035
    price_per_mithqal = price_per_gram * 5

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
def format_message():
    prices_data = get_gold_prices()
    if not prices_data:
        return "❌ تعذر جلب أسعار الذهب حالياً."

    prices = prices_data["karats"]
    ounce_price = prices_data["ounce"]

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"📅 {today}\n\n"
    msg += f"💰 أسعار الذهب الآن:\n• الأونصة: {ounce_price}$\n\n"
    for karat, (gram, mithqal) in prices.items():
        msg += f"{karat}:\n- للغرام: {gram}$\n- للمثقال: {mithqal}$\n\n"

    return msg

# إرسال الأسعار للقناة
async def send_prices():
    msg = format_message()
    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.HTML)

# إرسال الخطأ لحساب الأدمن
async def send_error(error_msg):
    try:
        if ADMIN_ID:  # نتأكد إنو موجود بالـ Secrets
            await bot.send_message(chat_id=int(ADMIN_ID), text=error_msg)
    except Exception as e:
        print("❌ فشل إرسال رسالة الخطأ:", e)

# الجدولة اليومية
async def scheduler():
    last_sent_hour = None
    while True:
        now = datetime.now()
        if 10 <= now.hour <= 17:  # من 10 الصبح لحد 5 العصر
            if now.minute == 0 and now.hour != last_sent_hour:
                await send_prices()
                last_sent_hour = now.hour
        await asyncio.sleep(30)

# تشغيل البوت
async def main():
    await scheduler()

if __name__ == "__main__":
    asyncio.run(main())
