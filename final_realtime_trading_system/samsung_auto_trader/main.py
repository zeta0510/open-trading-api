from __future__ import annotations

from dotenv import load_dotenv

from account import AccountService
from api_client import KisApiClient
from auth import AuthManager
from config import load_settings
from logger import setup_logger
from market_data import MarketDataService
from orders import OrderService
from trader import Trader


def main() -> None:
    """
    Program entry point.

    This program uses Korea Investment Open API mock trading environment only.
    Credentials must be provided through environment variables:
    - GH_ACCOUNT
    - GH_APPKEY
    - GH_APPSECRET
    """

    # Load .env file if it exists.
    # In GitHub Codespaces, you may also use terminal export commands.
    load_dotenv()

    logger = setup_logger()

    try:
        settings = load_settings()

        auth_manager = AuthManager(
            settings=settings,
            logger=logger,
        )

        api_client = KisApiClient(
            settings=settings,
            auth_manager=auth_manager,
            logger=logger,
        )

        market_data_service = MarketDataService(
            api_client=api_client,
            logger=logger,
        )

        account_service = AccountService(
            api_client=api_client,
            logger=logger,
        )

        order_service = OrderService(
            api_client=api_client,
            logger=logger,
        )

        trader = Trader(
            settings=settings,
            market_data_service=market_data_service,
            account_service=account_service,
            order_service=order_service,
            logger=logger,
        )

        trader.run()

    except KeyboardInterrupt:
        logger.info("Program interrupted by user.")

    except Exception as exc:
        logger.exception("Program terminated because of an unexpected error. error=%s", exc)
        raise


if __name__ == "__main__":
    main()
