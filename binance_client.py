import hmac
import hashlib
import time
from urllib.parse import urlencode
import requests


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
        response = requests.post(
            f"{self.BASE_URL}/fapi/v1/order", headers=headers, params=signed, timeout=10
        )
        response.raise_for_status()
        return response.json()

    def balance(self) -> float:
        """Return available USDT balance."""
        params = {"timestamp": int(time.time() * 1000)}
        signed = self._sign(params)
        headers = {"X-MBX-APIKEY": self.api_key}
        response = requests.get(
            f"{self.BASE_URL}/fapi/v2/balance", headers=headers, params=signed, timeout=10
        )
        response.raise_for_status()
        data = response.json()
        for entry in data:
            if entry.get("asset") == "USDT":
                return float(entry.get("availableBalance", 0.0))
        return 0.0
