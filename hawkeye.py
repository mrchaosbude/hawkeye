import os
import json
import requests
import telebot
import schedule
import time
import threading

# === KONFIGURATION ===
BINANCE_PRICE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
CONFIG_FILE = "config.json"
GITHUB_API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"telegram_token": "", "users": {}, "version": "1.0.0", "github_repo": "owner/repo"}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "telegram_token": TELEGRAM_TOKEN,
                "version": CURRENT_VERSION,
                "github_repo": GITHUB_REPO,
                "users": users,
            },
            f,
            indent=2,
        )


config = load_config()
TELEGRAM_TOKEN = config.get("telegram_token", "")
CURRENT_VERSION = config.get("version", "1.0.0")
GITHUB_REPO = config.get("github_repo", "owner/repo")
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


last_notified_version = CURRENT_VERSION


def get_latest_version():
    try:
        url = GITHUB_API_LATEST.format(repo=GITHUB_REPO)
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("tag_name")
    except Exception:
        return None


def check_for_update():
    global last_notified_version
    latest = get_latest_version()
    if not latest or latest in (CURRENT_VERSION, last_notified_version):
        return
    for cid in users.keys():
        bot.send_message(
            cid,
            f"🆕 Neue Version verfügbar: {latest} (aktuell {CURRENT_VERSION})",
        )
    last_notified_version = latest


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


# === JOB LOOP ===
schedule.every(5).minutes.do(check_price)
schedule.every(5).minutes.do(check_for_update)


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


threading.Thread(target=run_scheduler, daemon=True).start()

print("🤖 Bot läuft...")
bot.infinity_polling()

