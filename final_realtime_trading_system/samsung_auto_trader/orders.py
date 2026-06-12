from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from api_client import KisApiClient


# Mock trading domestic stock order endpoint.
# If endpoint or TR IDs differ in your KIS sample code, edit only these constants.
ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"

# Mock trading TR IDs
BUY_ORDER_TR_ID = "VTTC0802U"
SELL_ORDER_TR_ID = "VTTC0801U"

OrderSide = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: int
    price: int


@dataclass(frozen=True)
class OrderResult:
    symbol: str
    side: OrderSide
    quantity: int
    price: int
    success: bool
    order_number: str | None
    raw_response: dict[str, Any]


class OrderService:
    """
    Order service.

    This module submits mock-trading limit orders only.
    It does not assume live trading.
    """

    def __init__(self, api_client: KisApiClient, logger) -> None:
        self.api_client = api_client
        self.logger = logger

    def submit_limit_order(self, order: OrderRequest) -> OrderResult:
        """
        Submit a limit buy/sell order.

        Order type:
        - ORD_DVSN = "00" means limit order in KIS domestic stock API.
        """

        cano, acnt_prdt_cd = self._split_account_number()
        tr_id = BUY_ORDER_TR_ID if order.side == "BUY" else SELL_ORDER_TR_ID

        body = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": order.symbol,
            "ORD_DVSN": "00",
            "ORD_QTY": str(order.quantity),
            "ORD_UNPR": str(order.price),
        }

        self.logger.info(
            "%s order request. symbol=%s quantity=%s price=%s",
            order.side,
            order.symbol,
            order.quantity,
            order.price,
        )

        data = self.api_client.post(
            path=ORDER_CASH_PATH,
            tr_id=tr_id,
            json_body=body,
            use_hashkey=True,
            max_attempts=1,
        )

        result = self._parse_order_result(
            data=data,
            order=order,
        )

        if result.success:
            self.logger.info(
                "%s order submitted successfully. symbol=%s quantity=%s price=%s order_number=%s",
                order.side,
                order.symbol,
                order.quantity,
                order.price,
                result.order_number,
            )
        else:
            self.logger.warning(
                "%s order may have failed. symbol=%s quantity=%s price=%s response=%s",
                order.side,
                order.symbol,
                order.quantity,
                order.price,
                data,
            )

        return result

    def submit_buy_limit_order(
        self,
        symbol: str,
        quantity: int,
        price: int,
    ) -> OrderResult:
        return self.submit_limit_order(
            OrderRequest(
                symbol=symbol,
                side="BUY",
                quantity=quantity,
                price=price,
            )
        )

    def submit_sell_limit_order(
        self,
        symbol: str,
        quantity: int,
        price: int,
    ) -> OrderResult:
        return self.submit_limit_order(
            OrderRequest(
                symbol=symbol,
                side="SELL",
                quantity=quantity,
                price=price,
            )
        )

    def _split_account_number(self) -> tuple[str, str]:
        account = self.api_client.settings.account.strip().replace("-", "")

        if len(account) < 10:
            raise RuntimeError(
                "Invalid GH_ACCOUNT format. Expected at least 10 digits, "
                "for example 1234567801."
            )

        cano = account[:8]
        acnt_prdt_cd = account[8:10]

        return cano, acnt_prdt_cd

    def _parse_order_result(
        self,
        data: dict[str, Any],
        order: OrderRequest,
    ) -> OrderResult:
        """
        Parse order response.

        Common KIS response fields:
        - rt_cd == "0": success
        - output.KRX_FWDG_ORD_ORGNO
        - output.ODNO

        If the response shape differs, edit this method only.
        """

        rt_cd = str(data.get("rt_cd", ""))
        success = rt_cd == "0"

        output = data.get("output")
        order_number: str | None = None

        if isinstance(output, dict):
            order_number = output.get("ODNO") or output.get("odno")
            if order_number is not None:
                order_number = str(order_number)

        return OrderResult(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            success=success,
            order_number=order_number,
            raw_response=data,
        )
