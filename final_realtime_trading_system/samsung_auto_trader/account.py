from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api_client import KisApiClient


# Mock trading domestic stock balance inquiry.
# If endpoint or TR ID differs in your KIS sample code, edit only these constants.
INQUIRE_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
INQUIRE_BALANCE_TR_ID = "VTTC8434R"


@dataclass(frozen=True)
class Holding:
    symbol: str
    name: str
    quantity: int
    average_price: int
    current_price: int


@dataclass(frozen=True)
class AccountSnapshot:
    holdings: list[Holding] = field(default_factory=list)
    available_cash: int | None = None

    def get_holding_quantity(self, symbol: str) -> int:
        for holding in self.holdings:
            if holding.symbol == symbol:
                return holding.quantity
        return 0


class AccountService:
    """
    Account service.

    This module checks account balance and holdings.
    Because mock trading has strict request limits, this should not be called
    too frequently.
    """

    def __init__(self, api_client: KisApiClient, logger) -> None:
        self.api_client = api_client
        self.logger = logger

    def get_account_snapshot(self) -> AccountSnapshot:
        """
        Get account holdings and available cash.

        The account number format may differ by KIS account.
        Usually, account number is separated into:
        - CANO: first 8 digits
        - ACNT_PRDT_CD: last 2 digits

        Therefore, GH_ACCOUNT should be stored as a 10-digit string,
        for example: 1234567801
        """

        cano, acnt_prdt_cd = self._split_account_number()

        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        data = self.api_client.get(
            path=INQUIRE_BALANCE_PATH,
            tr_id=INQUIRE_BALANCE_TR_ID,
            params=params,
        )

        if str(data.get("rt_cd")) != "0":
            raise RuntimeError(
                f"Balance inquiry failed. msg_cd={data.get('msg_cd')} msg={data.get('msg1')}"
            )

        snapshot = self._parse_account_snapshot(data)

        self.logger.info(
            "Account snapshot checked. holdings_count=%s available_cash=%s",
            len(snapshot.holdings),
            snapshot.available_cash,
        )

        return snapshot

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

    def _parse_account_snapshot(self, data: dict[str, Any]) -> AccountSnapshot:
        """
        Parse KIS balance response.

        Common response fields:
        - output1: holdings list
        - output2: account summary list

        If the response shape differs, edit this method only.
        """

        output1 = data.get("output1", [])
        output2 = data.get("output2", [])


        holdings: list[Holding] = []

        if isinstance(output1, list):
            for item in output1:
                if not isinstance(item, dict):
                    continue

                symbol = str(item.get("pdno", "")).strip()
                if not symbol:
                    continue

                quantity = self._to_int(item.get("hldg_qty"))
                if quantity <= 0:
                    continue

                holding = Holding(
                    symbol=symbol,
                    name=str(item.get("prdt_name", "")).strip(),
                    quantity=quantity,
                    average_price=self._to_int(item.get("pchs_avg_pric")),
                    current_price=self._to_int(item.get("prpr")),
                )
                holdings.append(holding)

        available_cash: int | None = None

        if isinstance(output2, list) and output2:
            summary = output2[0]
            if isinstance(summary, dict):
                # This field may differ depending on the KIS response.
                # dnca_tot_amt: deposit/cash amount
                available_cash = self._to_int(summary.get("dnca_tot_amt"))

        return AccountSnapshot(
            holdings=holdings,
            available_cash=available_cash,
        )

    def _to_int(self, value: Any) -> int:
        if value is None:
            return 0

        text = str(value).replace(",", "").strip()
        if not text:
            return 0

        try:
            return int(float(text))
        except ValueError:
            return 0
