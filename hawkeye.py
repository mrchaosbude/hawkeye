import os
import json
import requests
import telebot
from telebot.apihelper import ApiException
import schedule
import time
import threading
import subprocess
import sys
import io
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mplfinance.original_flavor import candlestick_ohlc
from datetime import datetime
import logging

LOG_LEVEL_NAME = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL_NAME, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# === KONFIGURATION ===
BINANCE_PRICE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
CONFIG_FILE = "config.json"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
DB_FILE = "cache.db"
I18N_DIR = "i18n"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {
            "telegram_token": "",
            "users": {},
            "check_interval": 5,
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        data.pop("coingecko_api_key", None)
        return data


def save_config():
    data = {
        "telegram_token": TELEGRAM_TOKEN,
        "users": users,
        "check_interval": check_interval,
    }
    # optionalen trailing_percent-Schlüssel entfernen, wenn nicht gesetzt
    for cfg in data["users"].values():
        for sym_cfg in cfg.get("symbols", {}).values():
            if sym_cfg.get("trailing_percent") is None:
                sym_cfg.pop("trailing_percent", None)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS top10 (
                symbol TEXT PRIMARY KEY,
                id TEXT,
                name TEXT,
                cached_at INTEGER
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT,
                timestamp INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                PRIMARY KEY(symbol, timestamp)
            )
            """
        )
        conn.commit()


config = load_config()
TELEGRAM_TOKEN = config.get("telegram_token", "")
users = config.get("users", {})  # chat_id -> user data
check_interval = config.get("check_interval", 5)

bot = telebot.TeleBot(TELEGRAM_TOKEN)

init_db()

translations = {}


def load_translations():
    if not os.path.isdir(I18N_DIR):
        return
    for fname in os.listdir(I18N_DIR):
        if fname.endswith(".json"):
            code = fname.split(".")[0]
            with open(os.path.join(I18N_DIR, fname), encoding="utf-8") as f:
                translations[code] = json.load(f)


load_translations()


def get_user(chat_id):
    cid = str(chat_id)
    if cid not in users:
        users[cid] = {
            "symbols": {
                "BTCUSDT": {
                    "stop_loss": 42000.0,
                    "take_profit": 46000.0,
                    "trailing_percent": None,
                }
            },
            "notifications": True,
            "language": "de",
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
            "trailing_percent": None,
        }
        save_config()
    for sym_cfg in users[cid].get("symbols", {}).values():
        sym_cfg.setdefault("trailing_percent", None)
    users[cid].setdefault("language", "de")
    return users[cid]


def translate(chat_id, key, **kwargs):
    if chat_id is None:
        lang = "de"
    else:
        lang = get_user(chat_id).get("language", "de")
    text = translations.get(lang, {}).get(key, translations.get("en", {}).get(key, key))
    try:
        return text.format(**kwargs)
    except KeyError:
        return text


# === FUNKTIONEN ===
def get_price(sym):
    try:
        r = requests.get(
            BINANCE_PRICE_URL, params={"symbol": sym}, timeout=10
        )
        r.raise_for_status()
        price = float(r.json()["markPrice"])
        logger.debug("get_price %s -> %s", sym, price)
        return price
    except requests.Timeout:
        logger.error("get_price timeout for %s", sym)
        return None
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error("get_price error for %s: %s", sym, e)
        return None


def generate_buy_sell_chart(sym):
    """Erstellt ein Orderbuch-Diagramm mit den 20 oberen Kauf- und Verkaufsaufträgen."""
    try:
        # Orderbuch-Daten abrufen (20 Level)
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/depth",
            params={"symbol": sym, "limit": 20},
            timeout=10,
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
    except requests.Timeout:
        logger.error("generate_buy_sell_chart timeout for %s", sym)
        return None
    except (requests.RequestException, ValueError) as e:
        logger.error("generate_buy_sell_chart error for %s: %s", sym, e)
        return None


def get_top10_coingecko():
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
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        for coin in data:
            if "price_change_percentage_24h" not in coin:
                pct = coin.get("price_change_percentage_24h_in_currency")
                if pct is not None:
                    coin["price_change_percentage_24h"] = pct
        logger.debug("get_top10_coingecko returned %d coins", len(data))
        return data
    except requests.Timeout:
        logger.error("get_top10_coingecko timeout")
        return []
    except (requests.RequestException, ValueError) as e:
        logger.error("get_top10_coingecko error: %s", e)
        return []


def get_top10_binance():
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr", timeout=10
        )
        r.raise_for_status()
        tickers = r.json()
        top10 = sorted(
            tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True
        )[:10]
        coins = []
        for t in top10:
            coins.append(
                {
                    "name": t["symbol"],
                    "symbol": t["symbol"],
                    "current_price": float(t["lastPrice"]),
                    "price_change_percentage_24h": float(
                        t["priceChangePercent"]
                    ),
                }
            )
        logger.debug("get_top10_binance returned %d coins", len(coins))
        return coins
    except requests.Timeout:
        logger.error("get_top10_binance timeout")
        return []
    except (requests.RequestException, ValueError) as e:
        logger.error("get_top10_binance error: %s", e)
        return []


def get_top10_cryptos():
    coins = get_top10_coingecko()
    if coins:
        logger.debug(
            "get_top10_cryptos fetched %d coins from coingecko", len(coins)
        )
        return coins, "coingecko"
    logger.debug("get_top10_cryptos: falling back to binance")
    coins = get_top10_binance()
    return coins, "binance"


def generate_top10_chart(coins):
    """Erstellt Candlestick-Charts für die Top-10-Coins."""
    logger.debug("generate_top10_chart using coingecko")
    try:
        fig, axes = plt.subplots(5, 2, figsize=(10, 12))
        axes = axes.flatten()
        for ax, coin in zip(axes, coins):
            symbol = coin.get("symbol")
            logger.debug("Processing %s", symbol)
            ohlc_data = []
            coin_id = coin.get("id")
            backoff = 1
            max_attempts = 5
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(
                        "Requesting Coingecko OHLC for %s (attempt %d)",
                        coin_id,
                        attempt,
                    )
                    r = requests.get(
                        f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
                        params={"vs_currency": "usd", "days": 7},
                        timeout=10,
                    )
                    logger.debug("Coingecko status %s", r.status_code)
                    if r.status_code == 429:
                        wait = 60
                        logger.debug(
                            "429 for %s, sleeping %s s before retry", symbol, wait
                        )
                        time.sleep(wait)
                        backoff *= 2
                        continue
                    r.raise_for_status()
                    raw = r.json()
                    logger.debug(
                        "Coingecko returned %d entries for %s", len(raw), symbol
                    )
                    for t, o, h, l, c in raw:
                        ohlc_data.append(
                            [mdates.date2num(datetime.utcfromtimestamp(t / 1000)), o, h, l, c]
                        )
                    time.sleep(1)
                    break
                except requests.Timeout:
                    logger.error(
                        "Coingecko OHLC timeout for %s (attempt %d)",
                        symbol,
                        attempt,
                    )
                    if attempt == max_attempts:
                        ohlc_data = []
                        logger.debug(
                            "Failed to fetch OHLC for %s after %d attempts",
                            symbol,
                            max_attempts,
                        )
                    else:
                        wait = backoff
                        logger.debug(
                            "Retrying %s in %s s after timeout", symbol, wait
                        )
                        time.sleep(wait)
                        backoff *= 2
                except (requests.RequestException, ValueError) as e:
                    logger.error(
                        "Coingecko OHLC error for %s: %s (attempt %d)",
                        symbol,
                        e,
                        attempt,
                    )
                    if attempt == max_attempts:
                        ohlc_data = []
                        logger.debug(
                            "Failed to fetch OHLC for %s after %d attempts",
                            symbol,
                            max_attempts,
                        )
                    else:
                        wait = backoff
                        logger.debug("Retrying %s in %s s", symbol, wait)
                        time.sleep(wait)
                        backoff *= 2

            if ohlc_data:
                logger.debug(
                    "Plotting %s with %d entries", symbol, len(ohlc_data)
                )
                candlestick_ohlc(
                    ax,
                    ohlc_data,
                    colorup="green",
                    colordown="red",
                    width=0.6 / 24,
                )
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                logger.debug("No OHLC data for %s", symbol)
                ax.text(0.5, 0.5, translate(None, "no_data"), ha="center", va="center")
            ax.set_title(coin.get("symbol", "").upper())

        for ax in axes[len(coins):]:
            ax.axis("off")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except (ValueError, RuntimeError) as e:
        logger.error("generate_top10_chart error: %s", e)
        return None


def generate_binance_candlestick(symbol):
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": "1h", "limit": 24},
            timeout=10,
        )
        r.raise_for_status()
        raw = r.json()
        ohlc = [
            [
                mdates.date2num(datetime.utcfromtimestamp(item[0] / 1000)),
                float(item[1]),
                float(item[2]),
                float(item[3]),
                float(item[4]),
            ]
            for item in raw
        ]
        fig, ax = plt.subplots()
        candlestick_ohlc(
            ax, ohlc, colorup="green", colordown="red", width=0.6 / 24
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(symbol)
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except requests.Timeout:
        logger.error("generate_binance_candlestick timeout for %s", symbol)
        return None
    except (requests.RequestException, ValueError) as e:
        logger.error(
            "generate_binance_candlestick error for %s: %s", symbol, e
        )
        return None


def cache_top10_candles():
    logger.debug("cache_top10_candles start")
    coins = get_top10_coingecko()
    if not coins:
        logger.debug("cache_top10_candles: no coins returned")
        return
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM top10")
        cur.execute("DELETE FROM candles")
        now = int(time.time())
        for coin in coins:
            symbol = coin.get("symbol", "").upper()
            coin_id = coin.get("id")
            name = coin.get("name")
            cur.execute(
                "INSERT OR REPLACE INTO top10(symbol, id, name, cached_at) VALUES (?, ?, ?, ?)",
                (symbol, coin_id, name, now),
            )
            try:
                r = requests.get(
                    f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
                    params={"vs_currency": "usd", "days": 7},
                    timeout=10,
                )
                r.raise_for_status()
                raw = r.json()
                for t, o, h, l, c in raw:
                    cur.execute(
                        "INSERT OR REPLACE INTO candles(symbol, timestamp, open, high, low, close) VALUES (?, ?, ?, ?, ?, ?)",
                        (symbol, int(t / 1000), o, h, l, c),
                    )
                time.sleep(1)
            except requests.Timeout:
                logger.error(
                    "cache_top10_candles OHLC timeout for %s", symbol
                )
            except (requests.RequestException, sqlite3.Error, ValueError) as e:
                logger.error(
                    "cache_top10_candles OHLC error for %s: %s", symbol, e
                )
        conn.commit()


def load_cached_top10():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute("SELECT symbol, id, name FROM top10 ORDER BY rowid")
        rows = cur.fetchall()
    return [{"symbol": sym, "id": cid, "name": name} for sym, cid, name in rows]


def get_cached_ohlc(symbol):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT timestamp, open, high, low, close FROM candles WHERE symbol=? ORDER BY timestamp",
            (symbol,),
        )
        rows = cur.fetchall()
    ohlc = []
    for ts, o, h, l, c in rows:
        ohlc.append([mdates.date2num(datetime.utcfromtimestamp(ts)), o, h, l, c])
    return ohlc


def generate_top10_chart_cached(coins):
    try:
        fig, axes = plt.subplots(5, 2, figsize=(10, 12))
        axes = axes.flatten()
        for ax, coin in zip(axes, coins):
            symbol = coin.get("symbol", "").upper()
            ohlc_data = get_cached_ohlc(symbol)
            if ohlc_data:
                candlestick_ohlc(
                    ax,
                    ohlc_data,
                    colorup="green",
                    colordown="red",
                    width=0.6 / 24,
                )
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                ax.text(0.5, 0.5, translate(None, "no_data"), ha="center", va="center")
            ax.set_title(symbol)
        for ax in axes[len(coins):]:
            ax.axis("off")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except (ValueError, RuntimeError) as e:
        logger.error("generate_top10_chart_cached error: %s", e)
        return None


def generate_cached_candle_chart(symbol):
    """Erstellt ein Candlestick-Diagramm aus zwischengespeicherten Daten."""
    ohlc_data = get_cached_ohlc(symbol)
    if not ohlc_data:
        return None
    fig, ax = plt.subplots(figsize=(6, 4))
    candlestick_ohlc(
        ax,
        ohlc_data,
        colorup="green",
        colordown="red",
        width=0.6 / 24,
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def fetch_live_prices(coins):
    ids = ",".join([coin["id"] for coin in coins])
    try:
        r = requests.get(
            COINGECKO_MARKETS_URL,
            params={"vs_currency": "usd", "ids": ids},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        lookup = {item["symbol"].upper(): item for item in data}
        for coin in coins:
            sym = coin["symbol"].upper()
            info = lookup.get(sym)
            if info:
                coin["current_price"] = info.get("current_price")
                coin["price_change_percentage_24h"] = info.get(
                    "price_change_percentage_24h"
                ) or info.get("price_change_percentage_24h_in_currency")
    except requests.Timeout:
        logger.error("fetch_live_prices timeout")
    except (requests.RequestException, ValueError) as e:
        logger.error("fetch_live_prices error: %s", e)

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
                trailing = data.get("trailing_percent")
                if trailing is not None:
                    candidate_sl = price * (1 - trailing / 100)
                    if sl is None or sl <= 0:
                        data["stop_loss"] = candidate_sl
                        sl = candidate_sl
                        save_config()
                        bot.send_message(
                            cid,
                            translate(
                                cid,
                                "trailing_init",
                                symbol=sym,
                                sl=f"{sl:.2f}",
                                percent=trailing,
                            ),
                        )
                    elif price > sl and candidate_sl > sl:
                        data["stop_loss"] = candidate_sl
                        sl = candidate_sl
                        save_config()
                        bot.send_message(
                            cid,
                            translate(
                                cid,
                                "trailing_raise",
                                symbol=sym,
                                sl=f"{sl:.2f}",
                                percent=trailing,
                            ),
                        )
                if sl is not None and sl > 0 and price <= sl:
                    msg = (
                        translate(
                            cid,
                            "trailing_stop_reached",
                            price=price,
                            symbol=sym,
                        )
                        if trailing is not None
                        else translate(
                            cid, "stop_loss_reached", price=price, symbol=sym
                        )
                    )
                    bot.send_message(cid, msg)
                    chart = generate_buy_sell_chart(sym)
                    if chart:
                        bot.send_photo(cid, chart)
                elif tp is not None and tp > 0 and price >= tp:
                    bot.send_message(
                        cid,
                        translate(
                            cid,
                            "take_profit_reached",
                            price=price,
                            symbol=sym,
                        ),
                    )
                    chart = generate_buy_sell_chart(sym)
                    if chart:
                        bot.send_photo(cid, chart)
                percent = data.get("percent")
                base_price = data.get("base_price")
                if percent is not None and base_price is not None:
                    change = (price - base_price) / base_price * 100
                    if abs(change) >= percent:
                        direction = (
                            translate(cid, "direction_up")
                            if change > 0
                            else translate(cid, "direction_down")
                        )
                        bot.send_message(
                            cid,
                            translate(
                                cid,
                                "price_change",
                                symbol=sym,
                                base=f"{base_price:.2f}",
                                price=f"{price:.2f}",
                                direction=direction,
                                change=f"{change:+.2f}",
                                percent=percent,
                            ),
                        )
                        chart = generate_buy_sell_chart(sym)
                        if chart:
                            bot.send_photo(cid, chart)
                        data["base_price"] = price
                        save_config()


def check_updates():
    try:
        subprocess.run(
            ["git", "fetch"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        local = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        remote = subprocess.check_output(["git", "rev-parse", "@{u}"]).decode().strip()
        if local != remote:
            subprocess.run(["git", "pull"], check=True)
            os.execv(sys.executable, [sys.executable] + sys.argv)
    except (subprocess.SubprocessError, OSError) as e:
        logger.exception("Fehler beim Aktualisieren")
        for cid in users.keys():
            try:
                bot.send_message(cid, translate(cid, "update_error", e=e))
            except ApiException:
                logger.exception("Fehler beim Senden der Update-Fehlermeldung")


# === TELEGRAM COMMANDS ===
@bot.message_handler(commands=["set"])
def set_config(message):
    """Symbol-Konfiguration hinzufügen oder aktualisieren."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 3:
        bot.reply_to(message, translate(message.chat.id, "usage_set"))
        return
    new_symbol, new_stop_loss, new_take_profit = parts
    try:
        stop_loss = float(new_stop_loss)
        take_profit = float(new_take_profit)
    except ValueError:
        bot.reply_to(message, translate(message.chat.id, "set_number_error"))
        return
    entry = cfg.setdefault("symbols", {}).setdefault(new_symbol.upper(), {})
    entry["stop_loss"] = stop_loss
    entry["take_profit"] = take_profit
    save_config()
    bot.reply_to(
        message,
        translate(message.chat.id, "config_updated", symbol=new_symbol.upper()),
    )


@bot.message_handler(commands=["percent"])
def set_percent_command(message):
    """Prozentuale Preisänderung überwachen."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 2:
        bot.reply_to(message, translate(message.chat.id, "usage_percent"))
        return
    symbol, pct_str = parts
    try:
        percent = float(pct_str)
    except ValueError:
        bot.reply_to(message, translate(message.chat.id, "percent_nan"))
        return
    price = get_price(symbol.upper())
    if price is None:
        bot.reply_to(
            message, translate(message.chat.id, "price_fetch_error", symbol=symbol.upper())
        )
        return
    entry = cfg.setdefault("symbols", {}).setdefault(symbol.upper(), {})
    entry["percent"] = percent
    entry["base_price"] = price
    save_config()
    bot.reply_to(
        message,
        translate(
            message.chat.id,
            "percent_set",
            symbol=symbol.upper(),
            percent=percent,
            price=price,
        ),
    )


@bot.message_handler(commands=["trail"])
def set_trailing_command(message):
    """Trailing Stop-Loss setzen oder entfernen."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) == 0 or len(parts) > 2:
        bot.reply_to(message, translate(message.chat.id, "usage_trail"))
        return
    symbol = parts[0].upper()
    entry = cfg.setdefault("symbols", {}).setdefault(symbol, {})
    if len(parts) == 1:
        entry.pop("trailing_percent", None)
        save_config()
        bot.reply_to(
            message, translate(message.chat.id, "trailing_removed", symbol=symbol)
        )
        return
    try:
        percent = float(parts[1])
    except ValueError:
        bot.reply_to(message, translate(message.chat.id, "percent_nan_trail"))
        return
    if percent <= 0:
        entry.pop("trailing_percent", None)
        save_config()
        bot.reply_to(
            message, translate(message.chat.id, "trailing_removed", symbol=symbol)
        )
        return
    entry["trailing_percent"] = percent
    price = get_price(symbol)
    if price is not None:
        sl = price * (1 - percent / 100)
        entry["stop_loss"] = sl
        save_config()
        bot.reply_to(
            message,
            translate(
                message.chat.id,
                "trailing_set_sl",
                percent=percent,
                symbol=symbol,
                sl=f"{sl:.2f}",
            ),
        )
    else:
        save_config()
        bot.reply_to(
            message,
            translate(
                message.chat.id,
                "trailing_set",
                percent=percent,
                symbol=symbol,
            ),
        )


@bot.message_handler(commands=["remove"])
def remove_symbol(message):
    """Symbol-Konfiguration entfernen."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, translate(message.chat.id, "usage_remove"))
        return
    symbol = parts[0].upper()
    if symbol in cfg.get("symbols", {}):
        del cfg["symbols"][symbol]
        save_config()
        bot.reply_to(message, translate(message.chat.id, "symbol_removed", symbol=symbol))
    else:
        bot.reply_to(message, translate(message.chat.id, "symbol_not_found", symbol=symbol))


@bot.message_handler(commands=["interval"])
def set_interval_command(message):
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, translate(message.chat.id, "usage_interval"))
        return
    try:
        new_interval = int(parts[0])
        if new_interval <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, translate(message.chat.id, "interval_positive"))
        return
    global check_interval
    check_interval = new_interval
    save_config()
    schedule_jobs()
    bot.reply_to(
        message, translate(message.chat.id, "interval_set", minutes=new_interval)
    )


@bot.message_handler(commands=["now"])
def show_current_prices(message):
    cfg = get_user(message.chat.id)
    symbols = cfg.get("symbols", {})
    if not symbols:
        bot.reply_to(message, translate(message.chat.id, "no_symbols"))
        return
    lines = [translate(message.chat.id, "current_prices_header")]
    for sym in symbols:
        price = get_price(sym)
        if price is None:
            lines.append(
                translate(message.chat.id, "price_not_available", symbol=sym)
            )
        else:
            lines.append(f"{sym}: {price}")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["top10"])
def show_top10(message):
    coins = load_cached_top10()
    if not coins:
        cache_top10_candles()
        coins = load_cached_top10()
    if not coins:
        bot.reply_to(message, translate(message.chat.id, "top10_load_error"))
        return
    fetch_live_prices(coins)
    bot.send_message(message.chat.id, translate(message.chat.id, "top10_header"))
    for i, coin in enumerate(coins, start=1):
        symbol = coin.get("symbol", "").upper()
        price = coin.get("current_price")
        change = coin.get("price_change_percentage_24h")
        price_str = f"{price:.2f}" if isinstance(price, (int, float)) else "N/A"
        change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "N/A"
        caption = (
            f"{i}. {coin.get('name')} ({symbol}): {price_str} USD ({change_str})"
        )
        chart = generate_cached_candle_chart(symbol)
        if chart:
            bot.send_photo(message.chat.id, chart, caption=caption)
        else:
            bot.send_message(
                message.chat.id, caption + translate(message.chat.id, "no_chart_data")
            )


@bot.message_handler(commands=["history"])
def show_history(message):
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, translate(message.chat.id, "usage_history"))
        return
    symbol = parts[0].upper()
    chart = generate_binance_candlestick(symbol)
    if chart:
        bot.send_photo(message.chat.id, chart, caption=symbol)
    else:
        bot.reply_to(
            message, translate(message.chat.id, "history_error", symbol=symbol)
        )


@bot.message_handler(commands=["menu", "help"])
def show_menu(message):
    cfg = get_user(message.chat.id)
    status = (
        translate(message.chat.id, "notifications_on")
        if cfg.get("notifications", True)
        else translate(message.chat.id, "notifications_off")
    )
    lines = [
        translate(message.chat.id, "menu_header"),
        translate(message.chat.id, "menu_set"),
        translate(message.chat.id, "menu_remove"),
        translate(message.chat.id, "menu_percent"),
        translate(message.chat.id, "menu_stop"),
        translate(message.chat.id, "menu_start"),
        translate(message.chat.id, "menu_menu"),
        translate(message.chat.id, "menu_interval"),
        translate(message.chat.id, "menu_top10"),
        "",
        translate(message.chat.id, "menu_config_header"),
    ]
    for sym, data in cfg.get("symbols", {}).items():
        sl = data.get("stop_loss", "-")
        tp = data.get("take_profit", "-")
        line = translate(
            message.chat.id,
            "symbol_config",
            symbol=sym,
            sl=sl,
            tp=tp,
        )
        if "percent" in data:
            line += translate(
                message.chat.id,
                "symbol_config_percent",
                percent=data["percent"],
                base=data.get("base_price"),
            )
        lines.append(line)
    lines.append(translate(message.chat.id, "notifications_line", status=status))
    lines.append(
        translate(message.chat.id, "interval_line", minutes=check_interval)
    )
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=['stop'])
def stop_notifications(message):
    cfg = get_user(message.chat.id)
    cfg["notifications"] = False
    save_config()
    bot.reply_to(message, translate(message.chat.id, "notifications_stopped"))


@bot.message_handler(commands=['start'])
def start_notifications(message):
    cfg = get_user(message.chat.id)
    cfg["notifications"] = True
    save_config()
    bot.reply_to(message, translate(message.chat.id, "notifications_started"))


@bot.message_handler(commands=["language"])
def set_language_command(message):
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, translate(message.chat.id, "language_usage"))
        return
    code = parts[0]
    if code not in translations:
        bot.reply_to(message, translate(message.chat.id, "language_invalid", code=code))
        return
    cfg = get_user(message.chat.id)
    cfg["language"] = code
    save_config()
    bot.reply_to(message, translate(message.chat.id, "language_set", code=code))


# === JOB LOOP ===


def schedule_jobs():
    schedule.clear()
    schedule.every(check_interval).minutes.do(check_price)
    schedule.every(check_interval).minutes.do(check_updates)
    schedule.every().day.do(cache_top10_candles)


schedule_jobs()


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


threading.Thread(target=run_scheduler, daemon=True).start()

print(translate(None, "bot_running"))
bot.infinity_polling()

