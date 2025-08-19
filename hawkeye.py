import requests
import telebot
import schedule
import time

# === KONFIGURATION ===
BINANCE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
TELEGRAM_TOKEN = "DEIN_TELEGRAM_TOKEN"
CHAT_ID = "DEINE_CHAT_ID"

# Beispielwerte – später dynamisch aus GPT oder Datei
symbol = "BTCUSDT"
stop_loss = 42000.0
take_profit = 46000.0

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === FUNKTION: Kurs holen ===
def get_price(sym):
    try:
        r = requests.get(BINANCE_URL, params={"symbol": sym})
        r.raise_for_status()
        return float(r.json()["markPrice"])
    except Exception as e:
        return None

# === FUNKTION: Kurs prüfen ===
def check_price():
    global symbol, stop_loss, take_profit
    price = get_price(symbol)
    if price:
        if price <= stop_loss:
            bot.send_message(CHAT_ID, f"⚠ Stop-Loss erreicht bei {price} ({symbol})")
        elif price >= take_profit:
            bot.send_message(CHAT_ID, f"✅ Take-Profit erreicht bei {price} ({symbol})")

# === TELEGRAM COMMANDS ===
@bot.message_handler(commands=['set'])
def set_symbol(message):
    global symbol
    try:
        new_symbol = message.text.split()[1].upper()
        symbol = new_symbol
        bot.reply_to(message, f"Symbol geändert zu {symbol}")
    except:
        bot.reply_to(message, "⚠ Nutzung: /set SYMBOL (z. B. /set ETHUSDT)")

# === JOB LOOP ===
schedule.every(5).minutes.do(check_price)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

import threading
threading.Thread(target=run_scheduler, daemon=True).start()

print("🤖 Bot läuft...")
bot.infinity_polling()
