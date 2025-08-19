import os
import json
import hmac
import hashlib
from urllib.parse import urlencode
import requests
import telebot
import schedule
import time
import threading

# === KONFIGURATION ===
BINANCE_PRICE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_BALANCE_URL = "https://fapi.binance.com/fapi/v2/balance"
CONFIG_FILE = "config.json"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"telegram_token": "", "users": {}}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"telegram_token": TELEGRAM_TOKEN, "users": users}, f, indent=2)


config = load_config()
TELEGRAM_TOKEN = config.get("telegram_token", "")
users = config.get("users", {})  # chat_id -> user data

bot = telebot.TeleBot(TELEGRAM_TOKEN)


def get_user(chat_id):
    cid = str(chat_id)
    if cid not in users:
        users[cid] = {
            "symbol": "BTCUSDT",
            "stop_loss": 42000.0,
            "take_profit": 46000.0,
            "notifications": True,
            "api_key": "",
            "api_secret": "",
        }
        save_config()
    return users[cid]


# === FUNKTIONEN ===
def get_price(sym):
    try:
        r = requests.get(BINANCE_PRICE_URL, params={"symbol": sym})
        r.raise_for_status()
        return float(r.json()["markPrice"])
    except Exception:
        return None


def get_balance(api_key, api_secret):
    try:
        params = {"timestamp": int(time.time() * 1000)}
        query = urlencode(params)
        signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        params["signature"] = signature
        headers = {"X-MBX-APIKEY": api_key}
        r = requests.get(BINANCE_BALANCE_URL, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
        usdt = next((float(a["balance"]) for a in data if a.get("asset") == "USDT"), None)
        return usdt
    except Exception:
        return None


# === FUNKTIONEN: Checks ===
def check_price():
    for cid, cfg in users.items():
        if not cfg.get("notifications", True):
            continue
        price = get_price(cfg["symbol"])
        if price:
            if price <= cfg["stop_loss"]:
                bot.send_message(cid, f"⚠ Stop-Loss erreicht bei {price} ({cfg['symbol']})")
            elif price >= cfg["take_profit"]:
                bot.send_message(cid, f"✅ Take-Profit erreicht bei {price} ({cfg['symbol']})")


last_balances = {}


def check_balances():
    for cid, cfg in users.items():
        api_key = cfg.get("api_key")
        api_secret = cfg.get("api_secret")
        if not api_key or not api_secret:
            continue
        bal = get_balance(api_key, api_secret)
        if bal is None:
            continue
        prev = last_balances.get(cid)
        if prev is None or bal != prev:
            bot.send_message(cid, f"💰 Guthaben: {bal}")
            last_balances[cid] = bal


# === TELEGRAM COMMANDS ===
@bot.message_handler(commands=['set'])
def set_config(message):
    """Konfiguration für einen Nutzer setzen."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 3:
        bot.reply_to(
            message,
            "⚠ Nutzung: /set SYMBOL STOP_LOSS TAKE_PROFIT (z. B. /set ETHUSDT 40000 45000)",
        )
        return
    new_symbol, new_stop_loss, new_take_profit = parts
    try:
        cfg["stop_loss"] = float(new_stop_loss)
        cfg["take_profit"] = float(new_take_profit)
    except ValueError:
        bot.reply_to(
            message,
            "⚠ Stop-Loss und Take-Profit müssen Zahlen sein. Nutzung: /set SYMBOL STOP_LOSS TAKE_PROFIT",
        )
        return
    cfg["symbol"] = new_symbol.upper()
    save_config()
    bot.reply_to(
        message,
        f"✅ Konfiguration aktualisiert:\n"
        f"Symbol: {cfg['symbol']}\n"
        f"Stop-Loss: {cfg['stop_loss']}\n"
        f"Take-Profit: {cfg['take_profit']}",
    )


@bot.message_handler(commands=['menu', 'help'])
def show_menu(message):
    cfg = get_user(message.chat.id)
    status = "an" if cfg.get("notifications", True) else "aus"
    bot.reply_to(
        message,
        "📋 Menü:\n"
        "/set SYMBOL STOP_LOSS TAKE_PROFIT - Konfiguration setzen\n"
        "/register API_KEY API_SECRET - Binance Credentials speichern\n"
        "/stop - Benachrichtigungen deaktivieren\n"
        "/start - Benachrichtigungen aktivieren\n"
        "/menu - Dieses Menü anzeigen\n\n"
        f"Aktuelle Konfiguration:\n"
        f"Symbol: {cfg['symbol']}\n"
        f"Stop-Loss: {cfg['stop_loss']}\n"
        f"Take-Profit: {cfg['take_profit']}\n"
        f"Benachrichtigungen: {status}",
    )


@bot.message_handler(commands=['stop'])
def stop_notifications(message):
    cfg = get_user(message.chat.id)
    cfg["notifications"] = False
    save_config()
    bot.reply_to(message, "🔕 Benachrichtigungen deaktiviert. Tippe /start zum Aktivieren.")


@bot.message_handler(commands=['start'])
def start_notifications(message):
    cfg = get_user(message.chat.id)
    cfg["notifications"] = True
    save_config()
    bot.reply_to(message, "🔔 Benachrichtigungen aktiviert. Tippe /menu für Hilfe.")


@bot.message_handler(commands=['register'])
def register_user(message):
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 2:
        bot.reply_to(message, "⚠ Nutzung: /register API_KEY API_SECRET")
        return
    cfg["api_key"], cfg["api_secret"] = parts
    save_config()
    bot.reply_to(message, "✅ Credentials gespeichert.")


# === JOB LOOP ===
schedule.every(5).minutes.do(check_price)
schedule.every(5).minutes.do(check_balances)


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


threading.Thread(target=run_scheduler, daemon=True).start()

print("🤖 Bot läuft...")
bot.infinity_polling()

