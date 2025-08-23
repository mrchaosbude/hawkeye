import os
import json
import requests
import telebot
from telebot.apihelper import ApiException
try:
    from telebot.types import BotCommand
except Exception:  # pragma: no cover - fallback for stubbed telebot
    class BotCommand:  # minimal stub
        def __init__(self, command, description):
            self.command = command
            self.description = description
import schedule
import time
import threading
import subprocess
import sys
import io
from typing import Any
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mplfinance.original_flavor import candlestick_ohlc
from datetime import datetime
import logging
import pandas as pd
from strategies import get_strategy
from binance_client import BinanceClient
from autotrade_simulation import simulate_autotrade
from backtest import run_backtest

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

def fetch_json(url, params=None, timeout=10, max_retries=3, backoff_factor=1.0):
    """Perform a GET request and return parsed JSON.

    Errors are logged and ``None`` is returned on failure. A simple
    exponential backoff is used between retries.
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            status = getattr(resp, "status_code", 200)
            if status >= 400:
                msg = ""
                try:
                    body = resp.json()
                    if isinstance(body, dict):
                        msg = body.get("msg") or body.get("message") or str(body)
                    else:
                        msg = str(body)
                except Exception:
                    msg = getattr(resp, "text", "")
                raise Exception(msg)
            return resp.json()
        except Exception as exc:
            logger.error(
                "fetch_json error for %s (attempt %d/%d): %s",
                url,
                attempt,
                max_retries,
                exc,
            )
            if attempt == max_retries:
                break
            wait = backoff_factor * (2 ** (attempt - 1))
            time.sleep(wait)
    return None


def load_config() -> dict[str, Any]:
    """Load configuration from the JSON file.

    Parameters
    ----------
    None

    Returns
    -------
    dict[str, Any]
        Configuration dictionary with application settings.
    """
    if not os.path.exists(CONFIG_FILE):
        return {
            "telegram_token": "",
            "users": {},
            "check_interval": 5,
            "summary_time": "09:00",
            "strategy": "momentum",
            "strategy_params": {},
            "data_source": "binance",
            "binance_api_key": "",
            "binance_api_secret": "",
            "auto_stop": 0.0,
            "auto_takeprofit": 0.0,
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        data.pop("coingecko_api_key", None)
        data.setdefault("strategy", "momentum")
        data.setdefault("strategy_params", {})
        data.setdefault("data_source", "binance")
        data.setdefault("binance_api_key", "")
        data.setdefault("binance_api_secret", "")
        data.setdefault("auto_stop", 0.0)
        data.setdefault("auto_takeprofit", 0.0)
        for cfg in data.get("users", {}).values():
            cfg.setdefault("binance_api_key", "")
            cfg.setdefault("binance_api_secret", "")
        return data


def save_config() -> None:
    """Persist the current configuration to disk.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    data = {
        "telegram_token": TELEGRAM_TOKEN,
        "users": users,
        "check_interval": check_interval,
        "summary_time": summary_time,
        "strategy": strategy_name,
        "strategy_params": strategy_params,
        "data_source": data_source,
        "binance_api_key": BINANCE_API_KEY,
        "binance_api_secret": BINANCE_API_SECRET,
        "auto_stop": auto_stop,
        "auto_takeprofit": auto_takeprofit,
    }
    # optionalen trailing_percent-Schlüssel entfernen, wenn nicht gesetzt
    for cfg in data["users"].values():
        for sym_cfg in cfg.get("symbols", {}).values():
            if sym_cfg.get("trailing_percent") is None:
                sym_cfg.pop("trailing_percent", None)
            if sym_cfg.get("last_signal") is None:
                sym_cfg.pop("last_signal", None)
            if sym_cfg.get("trade_percent") is None:
                sym_cfg.pop("trade_percent", None)
            if sym_cfg.get("trade_amount", 0.0) == 0.0:
                sym_cfg.pop("trade_amount", None)
            if sym_cfg.get("quantity", 0.0) == 0.0:
                sym_cfg.pop("quantity", None)
            if sym_cfg.get("position", 0.0) == 0.0:
                sym_cfg.pop("position", None)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def init_db() -> None:
    """Initialize the SQLite cache database if necessary.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
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
summary_time = config.get("summary_time", "09:00")
strategy_name = config.get("strategy", "momentum")
strategy_params = config.get("strategy_params", {})
data_source = config.get("data_source", "binance")
BINANCE_API_KEY = config.get("binance_api_key", "")
BINANCE_API_SECRET = config.get("binance_api_secret", "")
auto_stop = config.get("auto_stop", 0.0)
auto_takeprofit = config.get("auto_takeprofit", 0.0)
strategy = get_strategy(strategy_name, **strategy_params)
binance_clients = {}

bot = telebot.TeleBot(TELEGRAM_TOKEN)

init_db()

translations = {}


def load_translations() -> None:
    """Load translation files from the ``i18n`` directory.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    if not os.path.isdir(I18N_DIR):
        return
    for fname in os.listdir(I18N_DIR):
        if fname.endswith(".json"):
            code = fname.split(".")[0]
            with open(os.path.join(I18N_DIR, fname), encoding="utf-8") as f:
                translations[code] = json.load(f)


load_translations()


def set_bot_commands():
    if not hasattr(bot, "set_my_commands"):
        return
    commands_by_lang = {}
    for lang, trans in translations.items():
        cmds = []
        for key, value in trans.items():
            if key.startswith("menu_") and key not in ("menu_header", "menu_config_header"):
                text = value.lstrip("/")
                parts = text.split(" - ", 1)
                if len(parts) < 2:
                    continue
                command_part, description = parts
                command = command_part.split()[0]
                cmds.append(BotCommand(command, description))
        if cmds:
            commands_by_lang[lang] = cmds
    if not commands_by_lang:
        return
    default_cmds = commands_by_lang.get("en") or next(iter(commands_by_lang.values()))
    bot.set_my_commands(default_cmds)
    for lang, cmds in commands_by_lang.items():
        if lang == "en" and cmds is default_cmds:
            continue
        bot.set_my_commands(cmds, language_code=lang)


set_bot_commands()


def get_user(chat_id):
    cid = str(chat_id)
    if cid not in users:
        users[cid] = {
            "symbols": {},
            "notifications": True,
            "language": "de",
            "role": "user",
            "max_symbols": 5,
            "binance_api_key": "",
            "binance_api_secret": "",
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
            "last_signal": None,
            "quantity": 0.0,
            "trade_amount": 0.0,
            "trade_percent": None,
        }
        save_config()
    for sym_cfg in users[cid].get("symbols", {}).values():
        sym_cfg.setdefault("trailing_percent", None)
        sym_cfg.setdefault("last_signal", None)
        sym_cfg.setdefault("quantity", 0.0)
        sym_cfg.setdefault("trade_amount", 0.0)
        sym_cfg.setdefault("trade_percent", None)
        sym_cfg.setdefault("position", 0.0)
    users[cid].setdefault("language", "de")
    users[cid].setdefault("role", "user")
    users[cid].setdefault("max_symbols", 5)
    users[cid].setdefault("binance_api_key", "")
    users[cid].setdefault("binance_api_secret", "")
    return users[cid]


def is_admin(chat_id):
    """Check if the user has admin role."""
    return get_user(chat_id).get("role") == "admin"


def get_binance_client(chat_id):
    cid = str(chat_id) if chat_id is not None else None
    key = BINANCE_API_KEY
    secret = BINANCE_API_SECRET
    if cid is not None:
        user = get_user(cid)
        key = user.get("binance_api_key") or key
        secret = user.get("binance_api_secret") or secret
    if not key or not secret:
        return None
    cache_key = cid or "global"
    client = binance_clients.get(cache_key)
    if (
        client
        and getattr(client, "api_key", None) == key
        and getattr(client, "api_secret", None) == secret
    ):
        return client
    client = BinanceClient(key, secret)
    binance_clients[cache_key] = client
    return client


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
    data = fetch_json(BINANCE_PRICE_URL, params={"symbol": sym})
    if data is None:
        return None
    try:
        price = float(data["markPrice"])
        logger.debug("get_price %s -> %s", sym, price)
        return price
    except (ValueError, KeyError, TypeError) as e:
        logger.error("get_price error for %s: %s", sym, e)
        return None


def generate_buy_sell_chart(sym):
    """Erstellt ein Orderbuch-Diagramm mit den 20 oberen Kauf- und Verkaufsaufträgen."""
    try:
        data = fetch_json(
            "https://fapi.binance.com/fapi/v1/depth",
            params={"symbol": sym, "limit": 20},
        )
        if not data:
            return None

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
    except (ValueError, KeyError, TypeError) as e:
        logger.error("generate_buy_sell_chart error for %s: %s", sym, e)
        return None


def get_top10_coingecko():
    data = fetch_json(
        COINGECKO_MARKETS_URL,
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 10,
            "page": 1,
            "price_change_percentage": "24h",
        },
    )
    if not data:
        return []
    for coin in data:
        if "price_change_percentage_24h" not in coin:
            pct = coin.get("price_change_percentage_24h_in_currency")
            if pct is not None:
                coin["price_change_percentage_24h"] = pct
    logger.debug("get_top10_coingecko returned %d coins", len(data))
    return data


def get_top10_binance():
    tickers = fetch_json("https://api.binance.com/api/v3/ticker/24hr")
    if not tickers:
        return []
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
            raw = fetch_json(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
                params={"vs_currency": "usd", "days": 7},
                max_retries=5,
            )
            if raw:
                logger.debug(
                    "Coingecko returned %d entries for %s", len(raw), symbol
                )
                for t, o, h, l, c in raw:
                    ohlc_data.append(
                        [mdates.date2num(datetime.utcfromtimestamp(t / 1000)), o, h, l, c]
                    )
                time.sleep(1)

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


BINANCE_PAIR_EXCEPTIONS = {
    # Stablecoins
    "USDT": None,
    "BUSD": "BUSDUSDT",
    "USDC": "USDCUSDT",
    "DAI": "DAIUSDT",
    # Assets without USDT pairs
    "WBTC": None,
}


def to_binance_pair(symbol: str):
    symbol = symbol.upper()
    return BINANCE_PAIR_EXCEPTIONS.get(symbol, f"{symbol}USDT")


def generate_binance_candlestick(pair):
    try:
        raw = fetch_json(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": pair, "interval": "1h", "limit": 24},
        )
        if not raw:
            return None
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
        ax.set_xlabel("Time (UTC)")
        ax.set_ylabel("Price")
        ax.set_title(pair)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except (ValueError, TypeError) as e:
        logger.error(
            "generate_binance_candlestick error for %s: %s", pair, e
        )
        return None


def get_daily_ohlcv_binance(sym, limit=400):
    raw = fetch_json(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": sym, "interval": "1d", "limit": limit},
    )
    if not raw:
        logger.error("Binance API error for %s", sym)
        return None
    try:
        rows = [
            {
                "Date": datetime.utcfromtimestamp(item[0] / 1000),
                "Open": float(item[1]),
                "High": float(item[2]),
                "Low": float(item[3]),
                "Close": float(item[4]),
                "Volume": float(item[5]),
            }
            for item in raw
        ]
        df = pd.DataFrame(rows).set_index("Date")
        return df
    except (ValueError, TypeError) as e:
        logger.error("get_daily_ohlcv_binance error for %s: %s", sym, e)
        return None


def get_daily_ohlcv_coinbase(sym, limit=400):
    product = sym.replace("USDT", "-USDT").replace("USD", "-USD")
    raw = fetch_json(
        f"https://api.exchange.coinbase.com/products/{product}/candles",
        params={"granularity": 86400},
    )
    if not raw:
        logger.error("Coinbase API error for %s", sym)
        return None
    try:
        rows = [
            {
                "Date": datetime.utcfromtimestamp(item[0]),
                "Open": float(item[3]),
                "High": float(item[2]),
                "Low": float(item[1]),
                "Close": float(item[4]),
                "Volume": float(item[5]),
            }
            for item in raw[:limit]
        ]
        df = pd.DataFrame(rows).set_index("Date").sort_index()
        return df
    except (ValueError, TypeError) as e:
        logger.error("get_daily_ohlcv_coinbase error for %s: %s", sym, e)
        return None


def get_daily_ohlcv(sym, limit=400):
    if data_source == "coinbase":
        return get_daily_ohlcv_coinbase(sym, limit)
    return get_daily_ohlcv_binance(sym, limit)


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
            raw = fetch_json(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
                params={"vs_currency": "usd", "days": 7},
                max_retries=5,
            )
            if raw:
                try:
                    for t, o, h, l, c in raw:
                        cur.execute(
                            "INSERT OR REPLACE INTO candles(symbol, timestamp, open, high, low, close) VALUES (?, ?, ?, ?, ?, ?)",
                            (symbol, int(t / 1000), o, h, l, c),
                        )
                    time.sleep(1)
                except (sqlite3.Error, ValueError, TypeError) as e:
                    logger.error(
                        "cache_top10_candles OHLC error for %s: %s", symbol, e
                    )
            else:
                logger.error(
                    "cache_top10_candles OHLC error for %s", symbol
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
    data = fetch_json(
        COINGECKO_MARKETS_URL,
        params={"vs_currency": "usd", "ids": ids},
    )
    if not data:
        return
    lookup = {item["symbol"].upper(): item for item in data}
    for coin in coins:
        sym = coin["symbol"].upper()
        info = lookup.get(sym)
        if info:
            coin["current_price"] = info.get("current_price")
            coin["price_change_percentage_24h"] = info.get(
                "price_change_percentage_24h"
            ) or info.get("price_change_percentage_24h_in_currency")


def record_simulated_trade(cfg, side, price, qty):
    """Update simulation state with a trade and return a status message."""
    balance = cfg.get("sim_balance", cfg.get("sim_start", 0.0))
    position = cfg.get("sim_position", 0.0)
    side_u = side.upper()
    if side_u == "BUY":
        balance -= price * qty
        position += qty
    elif side_u == "SELL":
        balance += price * qty
        position -= qty
    else:
        raise ValueError(f"unknown trade side: {side}")
    cfg["sim_balance"] = balance
    cfg["sim_position"] = position
    actions = cfg.setdefault("sim_actions", [])
    actions.append({"side": side_u, "price": price, "qty": qty})
    return simulate_autotrade(actions, cfg["sim_start"])[-1]

# === FUNKTIONEN: Checks ===
def check_price():
    benchmark = get_daily_ohlcv("BTCUSDT")
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

                # Signal-Änderungen überwachen
                try:
                    asset = get_daily_ohlcv(sym)
                    if asset is not None and benchmark is not None:
                        sigs = strategy.generate_signals(asset, benchmark)
                        signal = sigs.iloc[-1]["Signal"]
                        last_signal = data.get("last_signal")
                        if signal != last_signal:
                            if last_signal is not None:
                                bot.send_message(
                                    cid,
                                    translate(
                                        cid,
                                        "signal_changed",
                                        symbol=sym,
                                        old=translate(cid, f"signal_{last_signal}"),
                                        new=translate(cid, f"signal_{signal}"),
                                    ),
                                )
                            data["last_signal"] = signal
                            save_config()
                            client = get_binance_client(cid)
                            if signal in ("buy", "sell"):
                                price = get_price(sym)
                                if not price:
                                    continue
                                is_sim = data.get("sim_start") is not None
                                current_pos = data.get(
                                    "sim_position" if is_sim else "position", 0.0
                                )
                                amt = data.get("trade_amount", 0.0)
                                pct = data.get("trade_percent")
                                max_pct = data.get("max_percent")
                                balance = (
                                    data.get("sim_balance", data["sim_start"])
                                    if is_sim
                                    else client.balance() if client else 0.0
                                )
                                position_val = current_pos * price
                                equity = balance + position_val
                                if signal == "buy":
                                    if max_pct:
                                        max_val = equity * max_pct / 100
                                        allowed_val = max_val - position_val
                                        if allowed_val <= 0 or balance <= 0:
                                            continue
                                    else:
                                        if current_pos > 0:
                                            continue
                                        allowed_val = balance
                                    if pct and pct > 0:
                                        qty = balance * pct / 100 / price
                                    elif amt > 0:
                                        qty = amt / price
                                    elif data.get("quantity", 0.0) > 0:
                                        qty = data["quantity"]
                                    else:
                                        qty = 0.0
                                    if max_pct:
                                        qty = min(qty, allowed_val / price)
                                    if qty <= 0:
                                        continue
                                    if is_sim:
                                        msg = record_simulated_trade(data, "BUY", price, qty)
                                        bot.send_message(cid, msg)
                                    elif client:
                                        try:
                                            client.order(sym, "BUY", qty)
                                            data["position"] = current_pos + qty
                                            save_config()
                                            if auto_stop and auto_stop > 0:
                                                stop_price = price * (1 - auto_stop / 100)
                                                try:
                                                    client.place_protective_order(
                                                        sym, "SELL", qty, stop_price
                                                    )
                                                except Exception as exc:
                                                    logger.error(
                                                        "auto stop order error for %s: %s",
                                                        sym,
                                                        exc,
                                                    )
                                            if auto_takeprofit and auto_takeprofit > 0:
                                                tp_price = price * (1 + auto_takeprofit / 100)
                                                try:
                                                    client.place_protective_order(
                                                        sym, "SELL", qty, tp_price
                                                    )
                                                except Exception as exc:
                                                    logger.error(
                                                        "auto take-profit order error for %s: %s",
                                                        sym,
                                                        exc,
                                                    )
                                        except Exception as exc:
                                            logger.error("order error for %s: %s", sym, exc)
                                else:  # sell
                                    if current_pos <= 0:
                                        continue
                                    qty = current_pos
                                    if is_sim:
                                        msg = record_simulated_trade(data, "SELL", price, qty)
                                        bot.send_message(cid, msg)
                                    elif client:
                                        try:
                                            client.order(sym, "SELL", qty)
                                            data["position"] = max(0.0, current_pos - qty)
                                            save_config()
                                            if auto_stop and auto_stop > 0:
                                                stop_price = price * (1 + auto_stop / 100)
                                                try:
                                                    client.place_protective_order(
                                                        sym, "BUY", qty, stop_price
                                                    )
                                                except Exception as exc:
                                                    logger.error(
                                                        "auto stop order error for %s: %s",
                                                        sym,
                                                        exc,
                                                    )
                                            if auto_takeprofit and auto_takeprofit > 0:
                                                tp_price = price * (1 - auto_takeprofit / 100)
                                                try:
                                                    client.place_protective_order(
                                                        sym, "BUY", qty, tp_price
                                                    )
                                                except Exception as exc:
                                                    logger.error(
                                                        "auto take-profit order error for %s: %s",
                                                        sym,
                                                        exc,
                                                    )
                                        except Exception as exc:
                                            logger.error("order error for %s: %s", sym, exc)
                except Exception as e:
                    logger.error("check_price signal error for %s: %s", sym, e)


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


def send_daily_summary(chat_id=None):
    cids = [str(chat_id)] if chat_id is not None else list(users.keys())
    for cid in cids:
        cfg = get_user(cid)
        symbols = cfg.get("symbols", {})
        if not symbols:
            continue
        lines = [translate(cid, "daily_summary_header")]
        for sym in symbols:
            data = fetch_json(
                "https://fapi.binance.com/fapi/v1/ticker/24hr",
                params={"symbol": sym},
            )
            if data:
                try:
                    price = float(data.get("lastPrice"))
                    change = float(data.get("priceChangePercent"))
                    lines.append(f"{sym}: {price:.2f} ({change:+.2f}%)")
                except (TypeError, ValueError):
                    lines.append(
                        translate(cid, "price_not_available", symbol=sym)
                    )
            else:
                lines.append(translate(cid, "price_not_available", symbol=sym))
        bot.send_message(cid, "\n".join(lines))


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
    symbols = cfg.setdefault("symbols", {})
    symbol_upper = new_symbol.upper()
    if symbol_upper not in symbols and len(symbols) >= cfg.get("max_symbols", 5):
        bot.reply_to(
            message,
            translate(
                message.chat.id,
                "max_symbols_reached",
                max_symbols=cfg.get("max_symbols", 5),
            ),
        )
        return
    entry = symbols.setdefault(symbol_upper, {})
    entry["stop_loss"] = stop_loss
    entry["take_profit"] = take_profit
    save_config()
    bot.reply_to(
        message,
        translate(message.chat.id, "config_updated", symbol=symbol_upper),
    )


@bot.message_handler(commands=["watch"])
def watch_command(message):
    """Symbol für automatische Signalbenachrichtigungen hinzufügen."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, translate(message.chat.id, "usage_watch"))
        return
    symbol = parts[0].upper()
    symbols = cfg.setdefault("symbols", {})
    if symbol not in symbols and len(symbols) >= cfg.get("max_symbols", 5):
        bot.reply_to(
            message,
            translate(
                message.chat.id,
                "max_symbols_reached",
                max_symbols=cfg.get("max_symbols", 5),
            ),
        )
        return
    symbols.setdefault(symbol, {})
    save_config()
    bot.reply_to(
        message, translate(message.chat.id, "watch_added", symbol=symbol)
    )


@bot.message_handler(commands=["autotrade"])
def autotrade_command(message):
    """Configure automatic trading amount or percent for a symbol."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 2:
        bot.reply_to(message, translate(message.chat.id, "usage_autotrade"))
        return
    symbol, qty_str = parts[0].upper(), parts[1]
    sym_cfg = cfg.setdefault("symbols", {}).setdefault(symbol, {})
    if qty_str.endswith("%"):
        try:
            percent = float(qty_str[:-1])
        except ValueError:
            bot.reply_to(message, translate(message.chat.id, "autotrade_nan"))
            return
        sym_cfg["trade_percent"] = percent
        sym_cfg["trade_amount"] = 0.0
    else:
        try:
            amount = float(qty_str)
        except ValueError:
            bot.reply_to(message, translate(message.chat.id, "autotrade_nan"))
            return
        sym_cfg["trade_amount"] = amount
        sym_cfg["trade_percent"] = None
    save_config()
    bot.reply_to(
        message,
        translate(message.chat.id, "autotrade_set", symbol=symbol, qty=qty_str),
    )


@bot.message_handler(commands=["autotradelimit"])
def autotradelimit_command(message):
    """Set maximum portfolio percentage to allocate for a symbol."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 2 or not parts[1].endswith("%"):
        bot.reply_to(message, translate(message.chat.id, "usage_autotradelimit"))
        return
    symbol, pct_str = parts[0].upper(), parts[1]
    try:
        percent = float(pct_str[:-1])
    except ValueError:
        bot.reply_to(message, translate(message.chat.id, "autotradelimit_nan"))
        return
    sym_cfg = cfg.setdefault("symbols", {}).setdefault(symbol, {})
    sym_cfg["max_percent"] = percent
    save_config()
    bot.reply_to(
        message,
        translate(
            message.chat.id,
            "autotradelimit_set",
            symbol=symbol,
            percent=percent,
        ),
    )


@bot.message_handler(commands=["autotradesim"])
def autotradesim_command(message):
    """Configure simulated auto trading with starting balance."""
    cfg = get_user(message.chat.id)
    parts = message.text.split()[1:]
    if len(parts) != 3:
        bot.reply_to(message, translate(message.chat.id, "usage_autotradesim"))
        return
    start_str, symbol, qty_str = parts[0], parts[1].upper(), parts[2]
    try:
        start_balance = float(start_str)
    except ValueError:
        bot.reply_to(message, translate(message.chat.id, "autotradesim_nan"))
        return
    sym_cfg = cfg.setdefault("symbols", {}).setdefault(symbol, {})
    sym_cfg["sim_start"] = start_balance
    sym_cfg["sim_balance"] = start_balance
    sym_cfg["sim_position"] = 0.0
    sym_cfg["sim_actions"] = []
    if qty_str.endswith("%"):
        try:
            percent = float(qty_str[:-1])
        except ValueError:
            bot.reply_to(message, translate(message.chat.id, "autotrade_nan"))
            return
        sym_cfg["trade_percent"] = percent
        sym_cfg["trade_amount"] = 0.0
    else:
        try:
            amount = float(qty_str)
        except ValueError:
            bot.reply_to(message, translate(message.chat.id, "autotrade_nan"))
            return
        sym_cfg["trade_amount"] = amount
        sym_cfg["trade_percent"] = None
    save_config()
    bot.reply_to(
        message,
        translate(
            message.chat.id,
            "autotradesim_set",
            symbol=symbol,
            start=start_balance,
            qty=qty_str,
        ),
    )


@bot.message_handler(commands=["setkeys"])
def set_keys_command(message):
    """Set Binance API key and secret for the user."""
    parts = message.text.split()[1:]
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /setkeys API_KEY API_SECRET")
        return
    api_key, api_secret = parts
    cfg = get_user(message.chat.id)
    cfg["binance_api_key"] = api_key
    cfg["binance_api_secret"] = api_secret
    binance_clients.pop(str(message.chat.id), None)
    save_config()
    bot.reply_to(message, "✅ API keys updated.")


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
    symbol_upper = symbol.upper()
    symbols = cfg.setdefault("symbols", {})
    if symbol_upper not in symbols and len(symbols) >= cfg.get("max_symbols", 5):
        bot.reply_to(
            message,
            translate(
                message.chat.id,
                "max_symbols_reached",
                max_symbols=cfg.get("max_symbols", 5),
            ),
        )
        return
    price = get_price(symbol_upper)
    if price is None:
        bot.reply_to(
            message, translate(message.chat.id, "price_fetch_error", symbol=symbol_upper)
        )
        return
    entry = symbols.setdefault(symbol_upper, {})
    entry["percent"] = percent
    entry["base_price"] = price
    save_config()
    bot.reply_to(
        message,
        translate(
            message.chat.id,
            "percent_set",
            symbol=symbol_upper,
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
    symbols = cfg.setdefault("symbols", {})
    if (
        len(parts) > 1
        and symbol not in symbols
        and len(symbols) >= cfg.get("max_symbols", 5)
    ):
        bot.reply_to(
            message,
            translate(
                message.chat.id,
                "max_symbols_reached",
                max_symbols=cfg.get("max_symbols", 5),
            ),
        )
        return
    entry = symbols.setdefault(symbol, {})
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
    if not is_admin(message.chat.id):
        bot.reply_to(message, translate(message.chat.id, "admin_only"))
        return
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


@bot.message_handler(commands=["summarytime"])
def set_summary_time_command(message):
    if not is_admin(message.chat.id):
        bot.reply_to(message, translate(message.chat.id, "admin_only"))
        return
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, translate(message.chat.id, "usage_summarytime"))
        return
    time_str = parts[0]
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        bot.reply_to(message, translate(message.chat.id, "usage_summarytime"))
        return
    global summary_time
    summary_time = time_str
    save_config()
    schedule_jobs()
    bot.reply_to(message, translate(message.chat.id, "summary_time_set", time=time_str))


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


@bot.message_handler(commands=["summary"])
def summary_command(message):
    send_daily_summary(message.chat.id)


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
        if not chart:
            pair = to_binance_pair(symbol)
            if pair:
                chart = generate_binance_candlestick(pair)
            else:
                logger.info("No Binance pair for %s", symbol)
        if chart:
            bot.send_photo(message.chat.id, chart, caption=caption)
        else:
            bot.send_message(
                message.chat.id, caption + translate(message.chat.id, "no_chart_data")
            )


@bot.message_handler(commands=["portfolio"])
def cmd_portfolio(message):
    chat_id = message.chat.id
    cfg = get_user(chat_id)
    symbols = cfg.get("symbols", {})
    total_sim = 0.0
    trade_lines = []
    for sym, data in symbols.items():
        total_sim += data.get("sim_balance", 0.0)
        actions = data.get("sim_actions", [])
        if actions:
            qty = sum(a.get("qty", 0.0) for a in actions)
            trade_lines.append(f"{sym}: {qty:.4f}")
    client = get_binance_client(chat_id)
    real_balance = 0.0
    if client:
        try:
            real_balance = client.balance()
        except Exception as e:  # pragma: no cover - network error
            logger.error("cmd_portfolio balance error: %s", e)
    total = real_balance + total_sim
    trades = "\n".join(trade_lines) if trade_lines else translate(chat_id, "no_data")
    bot.reply_to(
        message,
        translate(
            chat_id,
            "portfolio_summary",
            total=total,
            binance=real_balance,
            sim=total_sim,
            trades=trades,
        ),
    )


@bot.message_handler(commands=["history"])
def show_history(message):
    parts = message.text.split()[1:]
    if len(parts) != 1:
        bot.reply_to(message, translate(message.chat.id, "usage_history"))
        return
    symbol = parts[0].upper()
    pair = to_binance_pair(symbol)
    if not pair:
        logger.info("No Binance pair for %s", symbol)
        bot.reply_to(
            message, translate(message.chat.id, "history_error", symbol=symbol)
        )
        return
    chart = generate_binance_candlestick(pair)
    if chart:
        bot.send_photo(message.chat.id, chart, caption=symbol)
    else:
        bot.reply_to(
            message, translate(message.chat.id, "history_error", symbol=symbol)
        )


@bot.message_handler(commands=["backtest"])
def backtest_command(message):
    parts = message.text.split()[1:]
    if len(parts) != 3:
        bot.reply_to(message, "Usage: /backtest SYMBOL START END")
        return
    symbol, start, end = parts[0].upper(), parts[1], parts[2]
    try:
        roi, drawdown = run_backtest(symbol, start, end)
        bot.reply_to(
            message,
            f"{symbol}: ROI {roi:.2%}, Max Drawdown {drawdown:.2%}",
        )
    except Exception as e:  # pragma: no cover - broad exception for user input
        logger.error("backtest command error for %s: %s", symbol, e)
        bot.reply_to(message, f"Backtest failed for {symbol}")

@bot.message_handler(commands=["signal"])
def signal_command(message):
    parts = message.text.split()[1:]
    if len(parts) not in (1, 2):
        bot.reply_to(message, translate(message.chat.id, "usage_signal"))
        return
    symbol = parts[0].upper()
    benchmark = parts[1].upper() if len(parts) == 2 else "BTCUSDT"
    asset = get_daily_ohlcv(symbol)
    bench = get_daily_ohlcv(benchmark)
    if asset is None or bench is None:
        bot.reply_to(message, translate(message.chat.id, "signal_error", symbol=symbol))
        return
    try:
        sigs = strategy.generate_signals(asset, bench)
        last = sigs.iloc[-1]
        sig_text = translate(message.chat.id, f"signal_{last['Signal']}")
        bot.reply_to(
            message,
            translate(
                message.chat.id,
                "signal_result",
                symbol=symbol,
                score=f"{last['Score']:.1f}",
                signal=sig_text,
            ),
        )
    except Exception as e:
        logger.error("signal_command error for %s: %s", symbol, e)
        bot.reply_to(message, translate(message.chat.id, "signal_error", symbol=symbol))


MENU_SECTIONS = {
    "symbol": ("menu_section_symbol", ["menu_set", "menu_remove", "menu_percent", "menu_trail", "menu_watch"]),
    "trading": ("menu_section_trading", ["menu_signal", "menu_autotrade", "menu_autotradesim", "menu_history", "menu_top10", "menu_portfolio"]),
    "system": ("menu_section_system", ["menu_stop", "menu_start", "menu_menu", "menu_interval", "menu_summarytime", "menu_now", "menu_summary", "menu_language"]),
}

@bot.message_handler(commands=["menu", "help"])
def show_menu(message):
    parts = message.text.split()[1:]
    section = parts[0].lower() if parts else None
    if section and section not in MENU_SECTIONS:
        bot.reply_to(message, translate(message.chat.id, "menu_section_invalid", section=section))
        return
    cfg = get_user(message.chat.id)
    status = (
        translate(message.chat.id, "notifications_on")
        if cfg.get("notifications", True)
        else translate(message.chat.id, "notifications_off")
    )
    lines = [translate(message.chat.id, "menu_header")]
    for key, (title_key, cmd_keys) in MENU_SECTIONS.items():
        if section and key != section:
            continue
        lines.append(translate(message.chat.id, title_key))
        for cmd in cmd_keys:
            lines.append(translate(message.chat.id, cmd))
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    if not section or section == "symbol":
        lines.append("")
        lines.append(translate(message.chat.id, "menu_config_header"))
        for sym, data in cfg.get("symbols", {}).items():
            sl = data.get("stop_loss", "-")
            tp = data.get("take_profit", "-")
            line = translate(message.chat.id, "symbol_config", symbol=sym, sl=sl, tp=tp)
            if "percent" in data:
                line += translate(message.chat.id, "symbol_config_percent", percent=data["percent"], base=data.get("base_price"))
            amt = data.get("trade_amount", 0.0)
            pct = data.get("trade_percent")
            max_pct = data.get("max_percent")
            if amt > 0:
                line += translate(message.chat.id, "symbol_config_trade_amount", amount=amt)
            if pct:
                line += translate(message.chat.id, "symbol_config_trade_percent", percent=pct)
            if max_pct:
                line += translate(message.chat.id, "symbol_config_max_percent", percent=max_pct)
            qty = data.get("quantity", 0.0)
            if qty > 0:
                line += translate(message.chat.id, "symbol_config_quantity", qty=qty)
            lines.append(line)
    lines.append(translate(message.chat.id, "notifications_line", status=status))
    lines.append(translate(message.chat.id, "interval_line", minutes=check_interval))
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
    if summary_time:
        schedule.every().day.at(summary_time).do(send_daily_summary)


schedule_jobs()


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


threading.Thread(target=run_scheduler, daemon=True).start()

print(translate(None, "bot_running"))
bot.infinity_polling()

