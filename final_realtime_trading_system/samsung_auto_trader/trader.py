from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from account import AccountService, AccountSnapshot
from config import Settings
from market_data import MarketDataService
from orders import OrderResult, OrderService


class Trader:
    """
    Polling-based Samsung Electronics mock auto-trader.

    Trading flow:
    1. Check Korean trading window
    2. Get current price
    3. Check account holdings and cash before order
    4. Submit buy order only if available cash is sufficient
    5. Submit sell order only if holding quantity is sufficient
    6. Check account holdings after order only when an order was submitted
    7. Sleep conservatively and repeat

    This trader uses REST API only.
    WebSocket is intentionally not used.
    """

    def __init__(
        self,
        settings: Settings,
        market_data_service: MarketDataService,
        account_service: AccountService,
        order_service: OrderService,
        logger,
    ) -> None:
        self.settings = settings
        self.market_data_service = market_data_service
        self.account_service = account_service
        self.order_service = order_service
        self.logger = logger
        self._should_stop = False

    def run(self) -> None:
        """
        Run the trading loop.

        The program does not place orders outside the Korean trading window.
        After 15:30 KST, the program stops automatically.
        """

        self.logger.info("Samsung auto trader started.")
        self.logger.info(
            "Trading target=%s window=%s~%s poll_interval=%ss offset=%s quantity=%s",
            self.settings.symbol,
            self.settings.trading_start,
            self.settings.trading_end,
            self.settings.poll_interval_seconds,
            self.settings.order_offset_krw,
            self.settings.order_quantity,
        )

        while True:
            now = datetime.now(ZoneInfo("Asia/Seoul")).time()

            if now < self.settings.trading_start:
                self.logger.info(
                    "Trading window has not started yet. now=%s start=%s",
                    now.strftime("%H:%M:%S"),
                    self.settings.trading_start,
                )
                self._sleep_until_next_poll()
                continue

            if now >= self.settings.trading_end:
                self.logger.info(
                    "Trading window ended. now=%s end=%s. Stopping trader.",
                    now.strftime("%H:%M:%S"),
                    self.settings.trading_end,
                )
                break

            self.logger.info("Trading window active. Starting one trading cycle.")

            try:
                self._run_one_cycle()
            except Exception as exc:
                self.logger.exception("Trading cycle failed. error=%s", exc)

            if self._should_stop:
                self.logger.info("Stop condition reached. Stopping trader.")
                break

            self._sleep_until_next_poll()

        self.logger.info("Samsung auto trader stopped.")

    def _run_one_cycle(self) -> None:
        """
        Execute one conservative polling-based trading cycle.

        API requests are minimized:
        - current price: 1 request
        - account before order: 1 request
        - buy/sell order: only when risk check passes
        - account after order: only when an order was submitted
        """

        symbol = self.settings.symbol
        quantity = self.settings.order_quantity
        offset = self.settings.order_offset_krw

        current_price = self.market_data_service.get_current_price(symbol).price

        raw_buy_price = max(current_price - offset, 1)
        raw_sell_price = current_price + offset

        buy_price = self._round_down_to_tick(raw_buy_price)
        sell_price = self._round_up_to_tick(raw_sell_price)

        self.logger.info(
            "Order prices calculated. current_price=%s raw_buy=%s buy_price=%s raw_sell=%s sell_price=%s",
            current_price,
            raw_buy_price,
            buy_price,
            raw_sell_price,
            sell_price,
        )

        before_snapshot = self.account_service.get_account_snapshot()
        self._log_snapshot(label="before_order", snapshot=before_snapshot, symbol=symbol)

        submitted_orders: list[OrderResult] = []

        if self._can_buy(before_snapshot, buy_price, quantity):
            buy_result = self.order_service.submit_buy_limit_order(
                symbol=symbol,
                quantity=quantity,
                price=buy_price,
            )
            submitted_orders.append(buy_result)
        else:
            self.logger.info(
                "BUY skipped by risk check. available_cash=%s required_cash=%s",
                before_snapshot.available_cash,
                buy_price * quantity,
            )

        if self._can_sell(before_snapshot, symbol, quantity):
            sell_result = self.order_service.submit_sell_limit_order(
                symbol=symbol,
                quantity=quantity,
                price=sell_price,
            )
            submitted_orders.append(sell_result)
        else:
            self.logger.info(
                "SELL skipped by risk check. holding_quantity=%s required_quantity=%s",
                before_snapshot.get_holding_quantity(symbol),
                quantity,
            )

        if not submitted_orders:
            self.logger.info(
                "No order submitted in this cycle. Skipping after-order balance check to reduce API usage."
            )
            return

        if self.settings.stop_after_first_successful_order:
            successful_orders = [order for order in submitted_orders if order.success]
            if successful_orders:
                self._should_stop = True
                self.logger.info(
                    "At least one order was submitted successfully. The trader will stop after this cycle."
                )

        after_snapshot = self.account_service.get_account_snapshot()
        self._log_snapshot(label="after_order", snapshot=after_snapshot, symbol=symbol)

        self._log_execution_check(
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            submitted_orders=submitted_orders,
            symbol=symbol,
        )

    def _can_buy(
        self,
        snapshot: AccountSnapshot,
        price: int,
        quantity: int,
    ) -> bool:
        required_cash = price * quantity

        if snapshot.available_cash is None:
            self.logger.info("BUY risk check failed: available cash is unknown.")
            return False

        return snapshot.available_cash >= required_cash

    def _can_sell(
        self,
        snapshot: AccountSnapshot,
        symbol: str,
        quantity: int,
    ) -> bool:
        return snapshot.get_holding_quantity(symbol) >= quantity

    def _log_snapshot(
        self,
        label: str,
        snapshot: AccountSnapshot,
        symbol: str,
    ) -> None:
        holding_quantity = snapshot.get_holding_quantity(symbol)

        self.logger.info(
            "Account snapshot %s. symbol=%s holding_quantity=%s available_cash=%s",
            label,
            symbol,
            holding_quantity,
            snapshot.available_cash,
        )

    def _log_execution_check(
        self,
        before_snapshot: AccountSnapshot,
        after_snapshot: AccountSnapshot,
        submitted_orders: list[OrderResult],
        symbol: str,
    ) -> None:
        """
        Estimate whether execution occurred by comparing holdings.

        Since WebSocket is not used, execution is inferred from updated account holdings.
        """

        before_quantity = before_snapshot.get_holding_quantity(symbol)
        after_quantity = after_snapshot.get_holding_quantity(symbol)
        quantity_diff = after_quantity - before_quantity

        self.logger.info(
            "Execution check. symbol=%s before_qty=%s after_qty=%s diff=%s",
            symbol,
            before_quantity,
            after_quantity,
            quantity_diff,
        )

        if quantity_diff > 0:
            self.logger.info(
                "Execution seems to have occurred: net BUY quantity increased by %s.",
                quantity_diff,
            )
        elif quantity_diff < 0:
            self.logger.info(
                "Execution seems to have occurred: net SELL quantity decreased by %s.",
                abs(quantity_diff),
            )
        else:
            self.logger.info(
                "No holding quantity change detected after submitted orders. "
                "Orders may be pending, rejected, or not executed yet."
            )

        for order in submitted_orders:
            self.logger.info(
                "Order submission summary. side=%s success=%s order_no=%s symbol=%s quantity=%s price=%s",
                order.side,
                order.success,
                order.order_number,
                order.symbol,
                order.quantity,
                order.price,
            )

    def _get_tick_size(self, price: int) -> int:
        """
        Return Korean domestic stock tick size.

        This table is used to avoid invalid order prices.
        For example, a price like 334250 is invalid when the tick size is 500.
        """

        if price < 2000:
            return 1
        if price < 5000:
            return 5
        if price < 20000:
            return 10
        if price < 50000:
            return 50
        if price < 100000:
            return 100
        if price < 500000:
            return 500
        return 1000

    def _round_down_to_tick(self, price: int) -> int:
        tick = self._get_tick_size(price)
        return max((price // tick) * tick, tick)

    def _round_up_to_tick(self, price: int) -> int:
        tick = self._get_tick_size(price)
        return ((price + tick - 1) // tick) * tick

    def _sleep_until_next_poll(self) -> None:
        seconds = self.settings.poll_interval_seconds
        self.logger.info("Sleeping for %s seconds to reduce API usage.", seconds)
        time.sleep(seconds)
