from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests

from config import Settings


@dataclass(frozen=True)
class TokenInfo:
    access_token: str
    cached_date: str


class AuthManager:
    """
    Korea Investment Open API authentication manager.

    The access token is cached in token_cache.json.
    If the cached token was created today, this manager reuses it.
    This design avoids unnecessary token issuance requests.
    """

    def __init__(self, settings: Settings, logger) -> None:
        self.settings = settings
        self.logger = logger
        self.cache_path = Path(settings.token_cache_path)

    def get_access_token(self) -> str:
        cached = self._load_cached_token()

        if cached is not None and cached.cached_date == date.today().isoformat():
            self.logger.info("Reusing cached access token for today.")
            return cached.access_token

        self.logger.info("No valid token cache found. Requesting new access token.")
        token = self._request_new_token()
        self._save_token(token)
        return token

    def _load_cached_token(self) -> TokenInfo | None:
        if not self.cache_path.exists():
            return None

        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            access_token = data.get("access_token")
            cached_date = data.get("cached_date")

            if not access_token or not cached_date:
                self.logger.warning("Token cache exists but is incomplete. Ignoring cache.")
                return None

            return TokenInfo(
                access_token=access_token,
                cached_date=cached_date,
            )

        except Exception as exc:
            self.logger.warning("Failed to read token cache. Ignoring cache. error=%s", exc)
            return None

    def _save_token(self, access_token: str) -> None:
        data = {
            "access_token": access_token,
            "cached_date": date.today().isoformat(),
        }
        self.cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.logger.info("Access token saved to token cache.")

    def _request_new_token(self) -> str:
        url = f"{self.settings.base_url}/oauth2/tokenP"

        payload: dict[str, Any] = {
            "grant_type": "client_credentials",
            "appkey": self.settings.app_key,
            "appsecret": self.settings.app_secret,
        }

        try:
            response = requests.post(
                url,
                headers={"content-type": "application/json; charset=utf-8"},
                json=payload,
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            self.logger.error("Token request timed out.")
            raise RuntimeError("Token request timed out.") from exc
        except requests.RequestException as exc:
            self.logger.error("Token request failed. error=%s", exc)
            raise RuntimeError("Token request failed.") from exc

        data = response.json()

        access_token = data.get("access_token")
        if not access_token:
            self.logger.error("Token response does not contain access_token. response=%s", data)
            raise RuntimeError("Token response does not contain access_token.")

        self.logger.info("New access token issued successfully.")
        return access_token
