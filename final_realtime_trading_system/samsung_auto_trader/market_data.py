from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api_client import KisApiClient


# Domestic stock current price inquiry
# If Korea Investment changes endpoint or TR ID, edit only these constants.
INQUIRE_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
INQUIRE_PRICE_TR_ID = "FHKST01010100"


@dataclass(frozen=True)
class CurrentPrice:
    symbol: str
    price: int


class MarketDataService:
    """
    Market data service.

    This module uses REST API polling only.
    WebSocket is intentionally not used.
    """

    def __init__(self, api_client: KisApiClient, logger) -> None:
        self.api_client = api_client
        self.logger = logger

    def get_current_price(self, symbol: str) -> CurrentPrice:
        """
        Get current market price for a domestic stock.

        Target:
        - Samsung Electronics: 005930
        """

        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": symbol,
        }

        data = self.api_client.get(
            path=INQUIRE_PRICE_PATH,
            tr_id=INQUIRE_PRICE_TR_ID,
            params=params,
        )

        price = self._extract_price(data)

        self.logger.info(
            "Current price checked. symbol=%s price=%s",
            symbol,
            price,
        )

        return CurrentPrice(symbol=symbol, price=price)

    def _extract_price(self, data: dict[str, Any]) -> int:
        """
        Extract current price from API response.

        Korea Investment current price response usually contains:
        output.stck_prpr

        If the response field name changes, update this method only.
        """

        output = data.get("output")
        if not isinstance(output, dict):
            raise RuntimeError(f"Unexpected current price response shape: {data}")

        raw_price = output.get("stck_prpr")
        if raw_price is None:
            raise RuntimeError(f"Current price field stck_prpr not found: {data}")

        try:
            return int(str(raw_price).replace(",", ""))
        except ValueError as exc:
            raise RuntimeError(f"Failed to parse current price: {raw_price}") from exc
