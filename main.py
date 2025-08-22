import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from PIL import Image, ImageDraw, ImageFont
import io
import asyncio
import os

# البيانات الخاصة بك
TOKEN = "8376047382:AAEGZxhQuSuqLWIIC240pWgpWOL_Vm0IINs"
CHAT_ID = "@iq_gold_price"  # يجب أن تبدأ بـ @ إذا كانت قناة عامة
GOLD_API_KEY = "goldapi-durssmemxt19z-io"

async def get_prices():
    # سعر الذهب بالدولار
    gold_url = f"https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLD_API_KEY}
    gold_data = requests.get(gold_url, headers=headers).json()
    gold_price = gold_data.get("price", None)

    # سعر صرف الدولار مقابل الدينار
    usd_iqd_url = "https://api.exchangerate.host/latest?base=USD&symbols=IQD"
    usd_iqd_data = requests.get(usd_iqd_url).json()
    usd_to_iqd = usd_iqd_data["rates"]["IQD"]

    # تحويل الذهب للدينار
    if gold_price:
        gold_price_iqd = gold_price * usd_to_iqd
    else:
        gold_price_iqd = None

    return round(gold_price, 2), round(usd_to_iqd, 2), round(gold_price_iqd, 0)

def create_image(gold_price_usd, usd_to_iqd, gold_price_iqd):
    img = Image.new('RGB', (700, 400), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", 40)

    text = f"💰 سعر الذهب اليوم\n\n🏅 الأونصة: ${gold_price_usd}\n💵 الدولار: {usd_to_iqd} IQD\n💰 الذهب بالدينار: {gold_price_iqd} IQD"
    draw.text((50, 100), text, fill=(255, 215, 0), font=font)

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gold_price_usd, usd_to_iqd, gold_price_iqd = await get_prices()
    img = create_image(gold_price_usd, usd_to_iqd, gold_price_iqd)
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img)

async def send_auto_price(app):
    while True:
        gold_price_usd, usd_to_iqd, gold_price_iqd = await get_prices()
        img = create_image(gold_price_usd, usd_to_iqd, gold_price_iqd)
        await app.bot.send_photo(chat_id=CHAT_ID, photo=img)
        await asyncio.sleep(1800)  # كل 30 دقيقة

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("price", price))

    # تشغيل التحديث التلقائي
    async def main():
        asyncio.create_task(send_auto_price(app))
        await app.run_polling()

    asyncio.run(main())
