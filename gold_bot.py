import os
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CallbackQueryHandler
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

# ===== صياغة الرسالة =====
def format_message(opening=False, closing=False):
    gold = get_gold_prices()
    msg = f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    if opening:
        msg += "✅ تم فتح بورصة العراق\n\n"
    elif closing:
        msg += "❌ تم اغلاق بورصة العراق\n\n"

    if gold:
        msg += "💰 أسعار الذهب بالدولار الأمريكي:\n"
        for karat in [24, 22, 21]:
            gram_price = gold[f'gram_{karat}']
            mitqal_price = gram_price * 4.25  # تحويل إلى مثقال
            msg += f"• عيار {karat}: {gram_price:.2f} $ للغرام | {mitqal_price:.2f} $ للمثقال\n"
        msg += f"• الأونصة: {gold['ounce']:.2f} $\n"
    else:
        msg += "❌ خطأ في جلب أسعار الذهب.\n"

    return msg

# ===== إرسال الأسعار للقناة مع زر الإنستغرام =====
async def send_prices_job(context: ContextTypes.DEFAULT_TYPE, opening=False, closing=False):
    msg = format_message(opening=opening, closing=closing)
    keyboard = [
        [InlineKeyboardButton("تابع الإنستغرام", url="https://www.instagram.com/aged_ali40?igsh=Nm42ZXVybTlia3Z0&utm_source=qr")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)

# ===== جدولة الرسائل =====
async def schedule_prices(app):
    # إرسال أول رسالة عند الساعة 10 صباحًا (فتح البورصة)
    app.job_queue.run_daily(lambda context: asyncio.create_task(send_prices_job(context, opening=True)),
                            time=time(10,0,0), days=(0,1,2,3,4,5,6))

    # إرسال باقي الرسائل كل ساعة من 11 صباحًا حتى 4 مساءً
    for hour in range(11, 17):
        app.job_queue.run_daily(lambda context: asyncio.create_task(send_prices_job(context)),
                                time=time(hour,0,0), days=(0,1,2,3,4,5,6))

    # إرسال آخر رسالة عند الساعة 5 مساءً (إغلاق البورصة)
    app.job_queue.run_daily(lambda context: asyncio.create_task(send_prices_job(context, closing=True)),
                            time=time(17,0,0), days=(0,1,2,3,4,5,6))

# ===== تشغيل البوت =====
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # جدولة الرسائل
    await schedule_prices(app)

    # تشغيل البوت
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
