import requests
import time
import telebot

# === KONFIG ===
BINANCE_API_URL = "https://fapi.binance.com/fapi/v1"
BITGET_API_URL = "https://api.bitget.com/api/mix/v1/market"

SYMBOL_BINANCE = "BTCUSDT"
SYMBOL_BITGET = "BTCUSDT_UMCBL"

# HIER DEIN TELEGRAM TOKEN + CHAT ID EINTRAGEN
TELEGRAM_TOKEN = "1234567890:ABCdefGhIJKlmNoPQrstUVwxyZ12345678"
TELEGRAM_CHAT_ID = "123456789"

# Telegram Bot init
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")


# === API Calls ===
def get_binance_price(symbol):
    try:
        url = f"{BINANCE_API_URL}/premiumIndex?symbol={symbol}"
        r = requests.get(url, timeout=5).json()
        return float(r["markPrice"])
    except Exception as e:
        print(f"Binance-Error: {e}")
        return None


def get_bitget_price(symbol):
    try:
        url = f"{BITGET_API_URL}/mark-price?symbol={symbol}"
        r = requests.get(url, timeout=5).json()
        return float(r["data"]["markPrice"])
    except Exception as e:
        print(f"Bitget-Error: {e}")
        return None


# === Alert senden ===
def send_alert():
    binance_price = get_binance_price(SYMBOL_BINANCE)
    bitget_price = get_bitget_price(SYMBOL_BITGET)

    msg_lines = []
    if binance_price:
        msg_lines.append(f"📊 Binance {SYMBOL_BINANCE}: {binance_price:.2f} USDT")
    if bitget_price:
        msg_lines.append(f"📊 Bitget {SYMBOL_BITGET}: {bitget_price:.2f} USDT")

    if msg_lines:
        msg = "🚨 Markt-Alarm 🚨\n\n" + "\n".join(msg_lines)
        bot.send_message(TELEGRAM_CHAT_ID, msg)
        print("✅ Alert gesendet.")
    else:
        print("⚠ Keine Daten erhalten, Alert übersprungen.")


# === Main Loop ===
if __name__ == "__main__":
    while True:
        send_alert()
        time.sleep(300)  # 300 Sekunden = 5 Minuten Intervall
