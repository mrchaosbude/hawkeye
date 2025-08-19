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
notifications_enabled = True

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
    global symbol, stop_loss, take_profit, notifications_enabled
    price = get_price(symbol)
    if price and notifications_enabled:
        if price <= stop_loss:
            bot.send_message(CHAT_ID, f"⚠ Stop-Loss erreicht bei {price} ({symbol})")
        elif price >= take_profit:
            bot.send_message(CHAT_ID, f"✅ Take-Profit erreicht bei {price} ({symbol})")

# === TELEGRAM COMMANDS ===
@bot.message_handler(commands=['set'])
def set_config(message):
    """Set trading configuration via Telegram command.

    Expected usage:
        /set SYMBOL STOP_LOSS TAKE_PROFIT

    Example:
        /set BTCUSDT 40000 45000
    """

    global symbol, stop_loss, take_profit

    parts = message.text.split()[1:]
    if len(parts) != 3:
        bot.reply_to(
            message,
            "⚠ Nutzung: /set SYMBOL STOP_LOSS TAKE_PROFIT (z. B. /set ETHUSDT 40000 45000)",
        )
        return

    new_symbol, new_stop_loss, new_take_profit = parts

    try:
        stop_loss = float(new_stop_loss)
        take_profit = float(new_take_profit)
    except ValueError:
        bot.reply_to(
            message,
            "⚠ Stop-Loss und Take-Profit müssen Zahlen sein. "
            "Nutzung: /set SYMBOL STOP_LOSS TAKE_PROFIT",
        )
        return

    symbol = new_symbol.upper()
    bot.reply_to(
        message,
        f"✅ Konfiguration aktualisiert:\n"
        f"Symbol: {symbol}\n"
        f"Stop-Loss: {stop_loss}\n"
        f"Take-Profit: {take_profit}",
    )


@bot.message_handler(commands=['menu', 'help'])
def show_menu(message):
    """Display available commands and current configuration."""
    global symbol, stop_loss, take_profit, notifications_enabled
    status = "an" if notifications_enabled else "aus"
    bot.reply_to(
        message,
        "📋 Menü:\n"
        "/set SYMBOL STOP_LOSS TAKE_PROFIT - Konfiguration setzen\n"
        "/stop - Benachrichtigungen deaktivieren\n"
        "/start - Benachrichtigungen aktivieren\n"
        "/menu - Dieses Menü anzeigen\n\n"
        f"Aktuelle Konfiguration:\n"
        f"Symbol: {symbol}\n"
        f"Stop-Loss: {stop_loss}\n"
        f"Take-Profit: {take_profit}\n"
        f"Benachrichtigungen: {status}",
    )


@bot.message_handler(commands=['stop'])
def stop_notifications(message):
    """Disable price alert notifications."""
    global notifications_enabled
    notifications_enabled = False
    bot.reply_to(message, "🔕 Benachrichtigungen deaktiviert. Tippe /start zum Aktivieren.")


@bot.message_handler(commands=['start'])
def start_notifications(message):
    """Enable price alert notifications and show menu."""
    global notifications_enabled
    notifications_enabled = True
    bot.reply_to(message, "🔔 Benachrichtigungen aktiviert. Tippe /menu für Hilfe.")

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
