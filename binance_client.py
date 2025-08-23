import hmac
import hashlib
import logging
import time
import threading
import json
from urllib.parse import urlencode

import requests
try:  # pragma: no cover - optional dependency in tests
    from requests.exceptions import RequestException, Timeout
except Exception:  # pragma: no cover - fallback when requests is stubbed
    class RequestException(Exception):
        """Fallback RequestException when requests is not fully available."""

        pass

    class Timeout(RequestException):
        """Fallback Timeout when requests is not fully available."""

        pass


logger = logging.getLogger(__name__)


class BinanceAPIError(Exception):
    """Raised when Binance API request fails."""


class BinanceClient:
    """Minimal Binance client for placing market orders."""

    BASE_URL = "https://fapi.binance.com"

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign(self, params: dict) -> dict:
        query = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def order(self, symbol: str, side: str, quantity: float) -> dict:
        """Place a market order on Binance."""
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
            "timestamp": int(time.time() * 1000),
        }
        signed = self._sign(params)
        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            response = requests.post(
                f"{self.BASE_URL}/fapi/v1/order",
                headers=headers,
                params=signed,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Timeout as exc:  # pragma: no cover - network timeout
            logger.error("Binance order request timed out for %s", symbol)
            raise BinanceAPIError("order request timed out") from exc
        except RequestException as exc:  # pragma: no cover - network error
            logger.error("Binance order request error for %s: %s", symbol, exc)
            raise BinanceAPIError(str(exc)) from exc

    def place_protective_order(
        self, symbol: str, side: str, quantity: float, stop_price: float
    ) -> dict:
        """Place a stop or take-profit market order.

        The order type is chosen based on ``stop_price`` relative to the
        current market price. When ``stop_price`` would realize a profit
        the order is sent as ``TAKE_PROFIT_MARKET``, otherwise as
        ``STOP_MARKET``.
        """

        order_type = "STOP_MARKET"
        try:
            resp = requests.get(
                f"{self.BASE_URL}/fapi/v1/ticker/price",
                params={"symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            price = float(resp.json().get("price", 0.0))
            if side.upper() == "SELL" and stop_price > price:
                order_type = "TAKE_PROFIT_MARKET"
            elif side.upper() == "BUY" and stop_price < price:
                order_type = "TAKE_PROFIT_MARKET"
        except Exception:
            # If fetching the current price fails, default to STOP_MARKET
            pass

        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type,
            "quantity": quantity,
            "stopPrice": stop_price,
            "timestamp": int(time.time() * 1000),
        }
        signed = self._sign(params)
        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            response = requests.post(
                f"{self.BASE_URL}/fapi/v1/order",
                headers=headers,
                params=signed,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Timeout as exc:  # pragma: no cover - network timeout
            logger.error(
                "Binance protective order request timed out for %s", symbol
            )
            raise BinanceAPIError("protective order request timed out") from exc
        except RequestException as exc:  # pragma: no cover - network error
            logger.error(
                "Binance protective order request error for %s: %s", symbol, exc
            )
            raise BinanceAPIError(str(exc)) from exc

    def balance(self) -> float:
        """Return available USDT balance."""
        params = {"timestamp": int(time.time() * 1000)}
        signed = self._sign(params)
        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            response = requests.get(
                f"{self.BASE_URL}/fapi/v2/balance",
                headers=headers,
                params=signed,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except Timeout as exc:  # pragma: no cover - network timeout
            logger.error("Binance balance request timed out")
            raise BinanceAPIError("balance request timed out") from exc
        except RequestException as exc:  # pragma: no cover - network error
            logger.error("Binance balance request error: %s", exc)
            raise BinanceAPIError(str(exc)) from exc
        for entry in data:
            if entry.get("asset") == "USDT":
                return float(entry.get("availableBalance", 0.0))
        return 0.0


try:  # pragma: no cover - optional dependency
    import websocket
except Exception:  # pragma: no cover - allow running without websocket-client
    websocket = None


class BinanceWebSocketClient:
    """Lightweight Binance WebSocket client for ticker updates.

    Prices received from the Binance futures WebSocket are stored in-memory
    and can be retrieved via :meth:`get_price`.
    """

    STREAM_URL = "wss://fstream.binance.com/ws"

    def __init__(self, symbols: list[str] | None = None) -> None:
        self.symbols = [s.lower() for s in (symbols or [])]
        self._prices: dict[str, float] = {}
        self._lock = threading.Lock()
        self.connected = False
        self._ws: websocket.WebSocketApp | None = None
        if websocket is not None:
            self._connect()
        else:  # pragma: no cover - when websocket-client isn't installed
            logger.warning("websocket-client library not available")

    def _connect(self) -> None:
        """Establish WebSocket connection and subscribe to streams."""

        def on_open(ws: websocket.WebSocketApp) -> None:
            self.connected = True
            if self.symbols:
                params = [f"{s}@ticker" for s in self.symbols]
                ws.send(
                    json.dumps(
                        {"method": "SUBSCRIBE", "params": params, "id": int(time.time())}
                    )
                )

        def on_message(ws: websocket.WebSocketApp, message: str) -> None:
            try:
                data = json.loads(message)
                if "stream" in data and "data" in data:
                    data = data["data"]
                symbol = data.get("s")
                price = data.get("c")
                if symbol and price:
                    with self._lock:
                        self._prices[symbol.upper()] = float(price)
            except Exception as exc:  # pragma: no cover - unexpected payloads
                logger.error("WebSocket message error: %s", exc)

        def on_error(ws: websocket.WebSocketApp, error: Exception) -> None:
            logger.error("WebSocket error: %s", error)

        def on_close(
            ws: websocket.WebSocketApp, close_status_code: int, close_msg: str
        ) -> None:
            self.connected = False
            logger.warning(
                "WebSocket closed: %s %s. Reconnecting...", close_status_code, close_msg
            )
            self._schedule_reconnect()

        self._ws = websocket.WebSocketApp(
            self.STREAM_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        threading.Thread(target=self._ws.run_forever, daemon=True).start()

    def _schedule_reconnect(self) -> None:
        """Attempt to reconnect after a short delay."""

        def runner() -> None:
            time.sleep(5)
            if websocket is not None:
                self._connect()

        threading.Thread(target=runner, daemon=True).start()

    def subscribe(self, symbol: str) -> None:
        """Subscribe to ticker updates for ``symbol``."""
        sym = symbol.lower()
        if sym in self.symbols:
            return
        self.symbols.append(sym)
        if self.connected and self._ws:
            try:
                self._ws.send(
                    json.dumps(
                        {"method": "SUBSCRIBE", "params": [f"{sym}@ticker"], "id": 1}
                    )
                )
            except Exception as exc:  # pragma: no cover - network send error
                logger.error("WebSocket subscribe error for %s: %s", sym, exc)

    def get_price(self, symbol: str) -> float | None:
        """Return last received price for ``symbol``."""
        with self._lock:
            return self._prices.get(symbol.upper())
