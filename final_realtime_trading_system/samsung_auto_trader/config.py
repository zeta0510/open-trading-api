from dataclasses import dataclass
from datetime import time
import os


@dataclass(frozen=True)
class Settings:
    """
    Project settings.

    Sensitive values are loaded from environment variables.
    Do not hardcode account number, app key, or app secret in source code.
    """

    account: str
    app_key: str
    app_secret: str

    # Korea Investment mock trading base URL
    base_url: str = "https://openapivts.koreainvestment.com:29443"

    # Trading target: Samsung Electronics
    symbol: str = "005930"

    # Conservative REST polling design
    poll_interval_seconds: int = 60

    # Order price offset.
    # The professor's prompt mentioned both 1000 and 2000 KRW.
    # We keep this as a configurable value.
    order_offset_krw: int = 1000

    # Very small order size for mock trading safety
    order_quantity: int = 1

    # Stop automatically after the first successfully submitted order.
    # This prevents repeated orders during testing.
    stop_after_first_successful_order: bool = True

    # Trading window
    trading_start: time = time(9, 10)
    trading_end: time = time(15, 30)

    # HTTP safety
    request_timeout_seconds: int = 10
    max_retries: int = 2
    api_min_interval_seconds: float = 2.0

    # Token cache path
    token_cache_path: str = "token_cache.json"


def load_settings() -> Settings:
    """
    Load credentials from environment variables.

    Required environment variables:
    - GH_ACCOUNT
    - GH_APPKEY
    - GH_APPSECRET
    """

    account = os.getenv("GH_ACCOUNT")
    app_key = os.getenv("GH_APPKEY")
    app_secret = os.getenv("GH_APPSECRET")

    missing = []
    if not account:
        missing.append("GH_ACCOUNT")
    if not app_key:
        missing.append("GH_APPKEY")
    if not app_secret:
        missing.append("GH_APPSECRET")

    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\nPlease set them before running the program."
        )

    return Settings(
        account=account,
        app_key=app_key,
        app_secret=app_secret,
    )
