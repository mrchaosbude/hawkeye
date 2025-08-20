import os
import json
import requests
import telebot
import schedule
import time
import threading
import subprocess
import sys
import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mplfinance.original_flavor import candlestick_ohlc
import datetime

# === KONFIGURATION ===
BINANCE_PRICE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
CONFIG_FILE = "config.json"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
COINMARKETCAP_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
COINPAPRIKA_URL = "https://api.coinpaprika.com/v1/tickers"
CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/top/mktcapfull"
BITGET_TICKERS_URL = "https://api.bitget.com/api/spot/v1/market/tickers"
BITGET_CANDLES_URL = "https://api.bitget.com/api/spot/v1/market/candles"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {
            "telegram_token": "",
            "users": {},
            "check_interval": 5,
            "coingecko_api_key": "",
            "coinmarketcap_api_key": "",
            "coinpaprika_api_key": "",
            "cryptocompare_api_key": "",
            "api_provider": "coingecko",
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "telegram_token": TELEGRAM_TOKEN,
                "users": users,
                "check_interval": check_interval,
                "coingecko_api_key": COINGECKO_API_KEY,
                "coinmarketcap_api_key": COINMARKETCAP_API_KEY,
                "coinpaprika_api_key": COINPAPRIKA_API_KEY,
                "cryptocompare_api_key": CRYPTOCOMPARE_API_KEY,
                "api_provider": API_PROVIDER,
            },
            f,
            indent=2,
        )


config = load_config()
TELEGRAM_TOKEN = config.get("telegram_token", "")
users = config.get("users", {})  # chat_id -> user data
check_interval = config.get("check_interval", 5)
COINGECKO_API_KEY = config.get("coingecko_api_key", "")
COINMARKETCAP_API_KEY = config.get("coinmarketcap_api_key", "")
COINPAPRIKA_API_KEY = config.get("coinpaprika_api_key", "")
CRYPTOCOMPARE_API_KEY = config.get("cryptocompare_api_key", "")
API_PROVIDER = config.get("api_provider", "coingecko")

bot = telebot.TeleBot(TELEGRAM_TOKEN)


def get_user(chat_id):
    cid = str(chat_id)
    if cid not in users:
        users[cid] = {
            "symbols": {
                "BTCUSDT": {"stop_loss": 42000.0, "take_profit": 46000.0}
            },
            "notifications": True,
        }
        save_config()
    # Sicherstellen, dass ältere Konfigurationen migriert werden
    if "symbol" in users[cid]:
        sym = users[cid].pop("symbol")
        sl = users[cid].pop("stop_loss", 0.0)
        tp = users[cid].pop("take_profit", 0.0)
        users[cid].setdefault("symbols", {})[sym] = {
            "stop_loss": sl,
            "take_profit": tp,
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


def generate_buy_sell_chart(sym):
    """Erstellt ein Orderbuch-Diagramm mit den 20 oberen Kauf- und Verkaufsaufträgen."""
    try:
        # Orderbuch-Daten abrufen (20 Level)
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/depth", params={"symbol": sym, "limit": 20}
        )
        r.raise_for_status()
        data = r.json()

        bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
        asks = [(float(p), float(q)) for p, q in data.get("asks", [])]
        if not bids or not asks:
            return None

        mid_price = (bids[0][0] + asks[0][0]) / 2

        fig, ax = plt.subplots()

        # Kaufaufträge (Bids) links vom Mid-Preis
        bid_prices = [p for p, _ in bids]
        bid_sizes = [q for _, q in bids]
        ax.bar(bid_prices, bid_sizes, color="green", label="Bids (Buy Orders)")

        # Verkaufsaufträge (Asks) rechts vom Mid-Preis
        ask_prices = [p for p, _ in asks]
        ask_sizes = [q for _, q in asks]
        ax.bar(ask_prices, ask_sizes, color="red", label="Asks (Sell Orders)")

        ax.axvline(mid_price, color="blue", linestyle="--", label=f"Mid Price {mid_price:.2f}")

        ax.set_title(f"{sym} – Orderbuch-Tiefe (20 Level)")
        ax.set_xlabel("Preis (USDT)")
        ax.set_ylabel("Ordergröße")
        ax.legend()
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        return None


def get_top10_coingecko():
    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
    try:
        r = requests.get(
            COINGECKO_MARKETS_URL,
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 10,
                "page": 1,
                "price_change_percentage": "24h",
            },
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        for coin in data:
            if "price_change_percentage_24h" not in coin:
                pct = coin.get("price_change_percentage_24h_in_currency")
                if pct is not None:
                    coin["price_change_percentage_24h"] = pct
        return data
    except Exception:
        return []


def get_top10_coinmarketcap():
    headers = {}
    if COINMARKETCAP_API_KEY:
        headers["X-CMC_PRO_API_KEY"] = COINMARKETCAP_API_KEY
    try:
        r = requests.get(
            COINMARKETCAP_URL,
            params={"start": 1, "limit": 10, "convert": "USD"},
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        coins = []
        for coin in data:
            quote = coin.get("quote", {}).get("USD", {})
            coins.append(
                {
                    "name": coin.get("name"),
                    "symbol": coin.get("symbol"),
                    "current_price": quote.get("price"),
                    "price_change_percentage_24h": quote.get("percent_change_24h"),
                }
            )
        return coins
    except Exception:
        return []


def get_top10_coinpaprika():
    try:
        r = requests.get(COINPAPRIKA_URL, params={"quotes": "USD"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        top = [c for c in data if c.get("rank", 0) and c["rank"] <= 10]
        coins = []
        for coin in top:
            quote = coin.get("quotes", {}).get("USD", {})
            coins.append(
                {
                    "id": coin.get("id"),
                    "name": coin.get("name"),
                    "symbol": coin.get("symbol"),
                    "current_price": quote.get("price"),
                    "price_change_percentage_24h": quote.get("percent_change_24h"),
                }
            )
        return coins
    except Exception:
        return []


def get_top10_cryptocompare():
    headers = {}
    if CRYPTOCOMPARE_API_KEY:
        headers["Authorization"] = f"Apikey {CRYPTOCOMPARE_API_KEY}"
    try:
        r = requests.get(
            CRYPTOCOMPARE_URL,
            params={"limit": 10, "tsym": "USD"},
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("Data", [])
        coins = []
        for item in data:
            info = item.get("CoinInfo", {})
            raw = item.get("RAW", {}).get("USD", {})
            coins.append(
                {
                    "name": info.get("FullName"),
                    "symbol": info.get("Name"),
                    "current_price": raw.get("PRICE"),
                    "price_change_percentage_24h": raw.get("CHANGEPCT24HOUR"),
                }
            )
        return coins
    except Exception:
        return []


def get_top10_bitget():
    try:
        r = requests.get(BITGET_TICKERS_URL, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        coins = []
        for item in data:
            sym = item.get("symbol")
            close = float(item.get("close", 0))
            open0 = float(item.get("openUtc0", 0))
            pct = None
            if open0:
                pct = (close - open0) / open0 * 100
            coins.append(
                {
                    "name": sym,
                    "symbol": sym,
                    "current_price": close,
                    "price_change_percentage_24h": pct,
                    "vol": float(item.get("usdtVol24h", 0)),
                }
            )
        coins.sort(key=lambda c: c.get("vol", 0), reverse=True)
        return coins[:10]
    except Exception:
        return []


def get_top10_cryptos():
    if API_PROVIDER == "coinmarketcap":
        return get_top10_coinmarketcap()
    if API_PROVIDER == "coinpaprika":
        return get_top10_coinpaprika()
    if API_PROVIDER == "cryptocompare":
        return get_top10_cryptocompare()
    if API_PROVIDER == "bitget":
        return get_top10_bitget()
    if API_PROVIDER == "coingecko":
        return get_top10_coingecko()
    return []


def generate_top10_chart(coins):
    """Erstellt Candlestick-Charts für die Top-10-Coins."""
    try:
        fig, axes = plt.subplots(5, 2, figsize=(10, 12))
        axes = axes.flatten()
        for ax, coin in zip(axes, coins):
            ohlc_data = []
            if API_PROVIDER == "coingecko":
                coin_id = coin.get("id")
                try:
                    r = requests.get(
                        f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
                        params={"vs_currency": "usd", "days": 1},
                        timeout=10,
                    )
                    r.raise_for_status()
                    raw = r.json()
                    for t, o, h, l, c in raw:
                        ohlc_data.append([mdates.epoch2num(t / 1000), o, h, l, c])
                except Exception:
                    ohlc_data = []
            elif API_PROVIDER == "coinmarketcap":
                symbol = coin.get("symbol")
                headers = {}
                if COINMARKETCAP_API_KEY:
                    headers["X-CMC_PRO_API_KEY"] = COINMARKETCAP_API_KEY
                try:
                    r = requests.get(
                        "https://pro-api.coinmarketcap.com/v2/cryptocurrency/ohlcv/historical",
                        params={"symbol": symbol, "count": 24, "interval": "1h"},
                        headers=headers,
                        timeout=10,
                    )
                    r.raise_for_status()
                    # Die CoinMarketCap-API liefert die Daten in einem
                    # nach Symbolen verschachtelten Objekt. Bisher wurde
                    # irrtümlich direkt auf "quotes" unter "data"
                    # zugegriffen, was stets zu einem leeren Ergebnis
                    # führte und somit keine Kerzen zeichnete. Wir holen
                    # nun explizit die Quotes für das angefragte Symbol.
                    raw = (
                        r.json()
                        .get("data", {})
                        .get(symbol, {})
                        .get("quotes", [])
                    )
                    for item in raw:
                        usd = item.get("quote", {}).get("USD", {})
                        o = usd.get("open")
                        h = usd.get("high")
                        l = usd.get("low")
                        c = usd.get("close")
                        t = item.get("time_open")
                        if None not in (t, o, h, l, c):
                            dt = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
                            ohlc_data.append([mdates.date2num(dt), o, h, l, c])
                except Exception:
                    ohlc_data = []
            elif API_PROVIDER == "coinpaprika":
                coin_id = coin.get("id")
                try:
                    start = (
                        datetime.datetime.utcnow() - datetime.timedelta(hours=24)
                    ).replace(microsecond=0).isoformat()
                    r = requests.get(
                        f"https://api.coinpaprika.com/v1/tickers/{coin_id}/historical",
                        params={"start": start, "interval": "1h", "limit": 24},
                        timeout=10,
                    )
                    r.raise_for_status()
                    raw = r.json()
                    for item in raw:
                        o = item.get("open")
                        h = item.get("high")
                        l = item.get("low")
                        c = item.get("close")
                        t = item.get("timestamp")
                        if None not in (t, o, h, l, c):
                            dt = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
                            ohlc_data.append([mdates.date2num(dt), o, h, l, c])
                except Exception:
                    ohlc_data = []
            elif API_PROVIDER == "cryptocompare":
                symbol = coin.get("symbol")
                headers = {}
                if CRYPTOCOMPARE_API_KEY:
                    headers["Authorization"] = f"Apikey {CRYPTOCOMPARE_API_KEY}"
                try:
                    r = requests.get(
                        "https://min-api.cryptocompare.com/data/v2/histohour",
                        params={"fsym": symbol, "tsym": "USD", "limit": 24},
                        headers=headers,
                        timeout=10,
                    )
                    r.raise_for_status()
                    # Die Struktur der Cryptocompare-Antwort variiert je
                    # nach Endpunkt. Um leere Datensätze zu vermeiden,
                    # akzeptieren wir sowohl die verschachtelte Form
                    # {"Data": {"Data": [...]}} als auch eine direkte
                    # Liste.
                    raw = r.json().get("Data", {})
                    if isinstance(raw, dict):
                        raw = raw.get("Data", [])
                    for item in raw or []:
                        t = item.get("time")
                        o = item.get("open")
                        h = item.get("high")
                        l = item.get("low")
                        c = item.get("close")
                        if None not in (t, o, h, l, c):
                            ohlc_data.append([mdates.epoch2num(t), o, h, l, c])
                except Exception:
                    ohlc_data = []
            elif API_PROVIDER == "bitget":
                symbol = coin.get("symbol")
                try:
                    r = requests.get(
                        BITGET_CANDLES_URL,
                        params={"symbol": symbol, "granularity": 3600, "limit": 24},
                        timeout=10,
                    )
                    r.raise_for_status()
                    raw = r.json().get("data", [])
                    # Bitget liefert die aktuellste Kerze zuerst
                    for item in reversed(raw):
                        t = int(item[0]) / 1000
                        o, h, l, c = map(float, item[1:5])
                        ohlc_data.append([mdates.epoch2num(t), o, h, l, c])
                except Exception:
                    ohlc_data = []

            if ohlc_data:
                candlestick_ohlc(
                    ax,
                    ohlc_data,
                    colorup="green",
                    colordown="red",
                    width=0.6 / 24,
                )
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                ax.text(0.5, 0.5, "Keine Daten", ha="center", va="center")
            ax.set_title(coin.get("symbol", "").upper())

        for ax in axes[len(coins):]:
            ax.axis("off")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        return None


# === FUNKTIONEN: Checks ===
def check_price():
    for cid, cfg in users.items():
        if not cfg.get("notifications", True):
            continue
        for sym, data in cfg.get("symbols", {}).items():
            price = get_price(sym)
            if price:
                sl = data.get("stop_loss")
                tp = data.get("take_profit")
                if sl is not None and sl > 0 and price <= sl:
                    bot.send_message(cid, f"⚠ Stop-Loss erreicht bei {price} ({sym})")
                    chart = generate_buy_sell_chart(sym)
                    if chart:
                        bot.send_photo(cid, chart)
                elif tp is not None and tp > 0 and price >= tp:
                    bot.send_message(cid, f"✅ Take-Profit erreicht bei {price} ({sym})")
                    chart = generate_buy_sell_chart(sym)
                    if chart:
                        bot.send_photo(cid, chart)
                percent = data.get("percent")
                base_price = data.get("base_price")
                if percent is not None and base_price is not None:
                    change = (price - base_price) / base_price * 100
                    if abs(change) >= percent:
                        direction = "gestiegen" if change > 0 else "gefallen"
                        bot.send_message(
                            cid,
                            (
                                f"📊 {sym}: Preis ist von {base_price:.2f} auf {price:.2f} {direction} "
                                f"({change:+.2f}%, Schwelle {percent}%). Basispreis aktualisiert."
                            ),
                        )
                        chart = generate_buy_sell_chart(sym)
                        if chart:
                            bot.send_photo(cid, chart)
                        data["base_price"] = price
                        save_config()


def check_updates():
    try:
        subprocess.run(["git", "fetch"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        local = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        remote = subprocess.check_output(["git", "rev-parse", "@{u}"]).decode().strip()
        if local != remote:
            subprocess.run(["git", "pull"], check=True)
            os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception:
        pass


# === TELEGRAM COMMANDS ===
@bot.message_handler(commands=["set"])
def set_config(message):
    """Symbol-Konfiguration hinzufügen oder aktualisieren."""
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
        stop_loss = float(new_stop_loss)
        take_profit = float(new_take_profit)
    except ValueError:
        bot.reply_to(
            message,
            "⚠ Stop-Loss und Take-Profit müssen Zahlen sein. Nutzung: /set SYMBOL STOP_LOSS TAKE_PROFIT",
        )
        return
    cfg.setdefault("symbols", {})[new_symbol.upper()] = {
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }
    save_config()
    bot.reply_to(
        message,
        f"✅ Konfiguration für {new_symbol.upper()} aktualisiert."
    )


@bot.message_handler(commands=["percent"])
def set_percent_command(message):
    """Prozentuale Preisänderung überwachen."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 2:
        bot.reply_to(message, "⚠ Nutzung: /percent SYMBOL PROZENT")
        return
    symbol, pct_str = parts
    try:
        percent = float(pct_str)
    except ValueError:
        bot.reply_to(message, "⚠ Prozent muss eine Zahl sein. Nutzung: /percent SYMBOL PROZENT")
        return
    price = get_price(symbol.upper())
    if price is None:
        bot.reply_to(message, f"⚠ Preis für {symbol.upper()} konnte nicht abgerufen werden.")
        return
    entry = cfg.setdefault("symbols", {}).setdefault(symbol.upper(), {})
    entry["percent"] = percent
    entry["base_price"] = price
    save_config()
    bot.reply_to(
        message,
        f"📊 Prozent-Alarm für {symbol.upper()} bei ±{percent}% gesetzt (Basis {price}).",
    )


@bot.message_handler(commands=["remove"])
def remove_symbol(message):
    """Symbol-Konfiguration entfernen."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, "⚠ Nutzung: /remove SYMBOL")
        return
    symbol = parts[0].upper()
    if symbol in cfg.get("symbols", {}):
        del cfg["symbols"][symbol]
        save_config()
        bot.reply_to(message, f"✅ {symbol} entfernt.")
    else:
        bot.reply_to(message, f"⚠ {symbol} nicht gefunden.")


@bot.message_handler(commands=["interval"])
def set_interval_command(message):
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, "⚠ Nutzung: /interval MINUTEN")
        return
    try:
        new_interval = int(parts[0])
        if new_interval <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "⚠ Intervall muss eine positive Ganzzahl sein.")
        return
    global check_interval
    check_interval = new_interval
    save_config()
    schedule_jobs()
    bot.reply_to(message, f"⏱ Prüfintervall auf {new_interval} Minuten gesetzt.")


@bot.message_handler(commands=["now"])
def show_current_prices(message):
    cfg = get_user(message.chat.id)
    symbols = cfg.get("symbols", {})
    if not symbols:
        bot.reply_to(message, "⚠ Keine Symbole konfiguriert.")
        return
    lines = ["📈 Aktuelle Preise:"]
    for sym in symbols:
        price = get_price(sym)
        if price is None:
            lines.append(f"{sym}: Preis nicht verfügbar")
        else:
            lines.append(f"{sym}: {price}")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["top10"])
def show_top10(message):
    coins = get_top10_cryptos()
    if not coins:
        bot.reply_to(message, "⚠ Top 10 konnten nicht geladen werden.")
        return
    lines = ["🏆 Top 10 Kryptowährungen:"]
    for i, coin in enumerate(coins, start=1):
        price = coin.get("current_price")
        change = coin.get("price_change_percentage_24h")
        if change is None:
            change = coin.get("price_change_percentage_24h_in_currency")

        price_str = f"{price:.2f}" if isinstance(price, (int, float)) else "N/A"
        change_str = (
            f"{change:+.2f}%" if isinstance(change, (int, float)) else "N/A"
        )

        lines.append(
            f"{i}. {coin.get('name')} ({coin.get('symbol', '').upper()}): {price_str} USD ({change_str})"
        )
    chart = generate_top10_chart(coins)
    text = "\n".join(lines)
    if chart:
        bot.send_photo(message.chat.id, chart, caption=text)
    else:
        bot.reply_to(message, text)


@bot.message_handler(commands=["menu", "help"])
def show_menu(message):
    cfg = get_user(message.chat.id)
    status = "an" if cfg.get("notifications", True) else "aus"
    lines = [
        "📋 Menü:",
        "/set SYMBOL STOP_LOSS TAKE_PROFIT - Symbol hinzufügen/ändern",
        "/remove SYMBOL - Symbol entfernen",
        "/percent SYMBOL PROZENT - Alarm bei ±PROZENT Preisänderung",
        "/stop - Benachrichtigungen deaktivieren",
        "/start - Benachrichtigungen aktivieren",
        "/menu - Dieses Menü anzeigen",
        "/interval MINUTEN - Prüfintervall setzen",
        "/top10 - Top 10 Kryptowährungen anzeigen",
        "",
        "Aktuelle Konfiguration:",
    ]
    for sym, data in cfg.get("symbols", {}).items():
        sl = data.get("stop_loss", "-")
        tp = data.get("take_profit", "-")
        line = f"{sym}: Stop-Loss {sl}, Take-Profit {tp}"
        if "percent" in data:
            line += f", Prozent-Alarm {data['percent']}% (Basis {data.get('base_price')})"
        lines.append(line)
    lines.append(f"Benachrichtigungen: {status}")
    lines.append(f"Prüfintervall: {check_interval} Minuten")
    bot.reply_to(message, "\n".join(lines))


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


def schedule_jobs():
    schedule.clear()
    schedule.every(check_interval).minutes.do(check_price)
    schedule.every(check_interval).minutes.do(check_updates)


schedule_jobs()


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


threading.Thread(target=run_scheduler, daemon=True).start()

print("🤖 Bot läuft...")
bot.infinity_polling()

