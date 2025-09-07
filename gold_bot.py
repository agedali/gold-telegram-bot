import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

# --- المتغيرات من GitHub Secrets ---
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLDAPI_KEY = os.getenv("GOLDPRICEZ_KEY")


# --- سحب سعر الدولار واليورو من موقع عراقي ---
def get_fx_rates():
    try:
        url = "https://www.iqiraq.news/economy/69957--143500-.html"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        rates = {}

        table = soup.find("table")
        if not table:
            return {}

        for row in table.find_all("tr"):
            cols = [c.text.strip().replace(",", "").replace(" ", "") for c in row.find_all("td")]
            if len(cols) >= 3:
                currency, buy, sell = cols[0], cols[1], cols[2]
                if "دولار" in currency or "USD" in currency:
                    rates["USD"] = {"buy": float(buy), "sell": float(sell)}
                if "يورو" in currency or "EUR" in currency:
                    rates["EUR"] = {"buy": float(buy), "sell": float(sell)}
        return rates
    except Exception as e:
        print("❌ Error fetching FX rates:", e)
        return {}


# --- سحب أسعار الذهب من GoldAPI ---
def get_gold_prices(iqd_rate):
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        gram_24_usd = data['price_gram_24k']
        ounce_usd = data['price']

        return {
            "gram_24_usd": gram_24_usd,
            "gram_22_usd": gram_24_usd * 22 / 24,
            "gram_21_usd": gram_24_usd * 21 / 24,
            "ounce_usd": ounce_usd,
            # بالـ IQD
            "gram_24_iqd": gram_24_usd * iqd_rate,
            "gram_22_iqd": gram_24_usd * 22 / 24 * iqd_rate,
            "gram_21_iqd": gram_24_usd * 21 / 24 * iqd_rate,
            "ounce_iqd": ounce_usd * iqd_rate,
        }
    except Exception as e:
        print("❌ Error fetching gold prices:", e)
        return None


# --- صياغة الرسالة ---
def format_message():
    fx = get_fx_rates()
    if not fx or "USD" not in fx:
        return "❌ خطأ في جلب أسعار الصرف."

    usd_rate = fx["USD"]["sell"]  # سعر البيع بالدينار
    gold = get_gold_prices(usd_rate)
    if not gold:
        return "❌ خطأ في جلب أسعار الذهب."

    msg = f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    msg += "💰 أسعار الذهب:\n"
    msg += f"• 24k: {gold['gram_24_usd']:.2f} $ | {gold['gram_24_iqd']:.0f} IQD\n"
    msg += f"• 22k: {gold['gram_22_usd']:.2f} $ | {gold['gram_22_iqd']:.0f} IQD\n"
    msg += f"• 21k: {gold['gram_21_usd']:.2f} $ | {gold['gram_21_iqd']:.0f} IQD\n"
    msg += f"• الأونصة: {gold['ounce_usd']:.2f} $ | {gold['ounce_iqd']:.0f} IQD\n\n"

    msg += "💱 أسعار العملات مقابل الدينار العراقي:\n"
    for curr, vals in fx.items():
        msg += f"• {curr}: شراء {vals['buy']} | بيع {vals['sell']}\n"

    return msg


# --- إرسال الأسعار مع زر ---
async def send_prices(bot):
    msg = format_message()
    keyboard = [[InlineKeyboardButton("📊 حساب الأرباح", callback_data="calc_profit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=reply_markup)


# --- زر حساب الأرباح ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "calc_profit":
        await query.edit_message_text(
            text="💡 أدخل عدد الغرامات التي اشتريتها (مثال: 10)"
        )


# --- تشغيل البوت ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # زر حساب الأرباح
    app.add_handler(CallbackQueryHandler(button_handler))

    # إرسال الأسعار عند التشغيل
    await send_prices(app.bot)

    print("✅ Bot is running...")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
