from __future__ import annotations

import time
from typing import Any, Literal

import requests

from auth import AuthManager
from config import Settings


HttpMethod = Literal["GET", "POST"]


class KisApiClient:
    """
    Common REST API client for Korea Investment Open API.

    This class is responsible for:
    - attaching authentication headers
    - generating hashkey for order requests
    - sending GET/POST requests
    - handling timeout and retry
    - throttling requests to avoid mock trading rate limits
    - logging API failures

    Trading logic should not be implemented here.
    """

    def __init__(self, settings: Settings, auth_manager: AuthManager, logger) -> None:
        self.settings = settings
        self.auth_manager = auth_manager
        self.logger = logger
        self._last_request_time: float | None = None

    def get(
        self,
        path: str,
        tr_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            method="GET",
            path=path,
            tr_id=tr_id,
            params=params,
            json_body=None,
            use_hashkey=False,
            max_attempts=self.settings.max_retries + 1,
        )

    def post(
        self,
        path: str,
        tr_id: str,
        json_body: dict[str, Any] | None = None,
        use_hashkey: bool = False,
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        return self._request(
            method="POST",
            path=path,
            tr_id=tr_id,
            params=None,
            json_body=json_body,
            use_hashkey=use_hashkey,
            max_attempts=max_attempts or self.settings.max_retries + 1,
        )

    def _request(
        self,
        method: HttpMethod,
        path: str,
        tr_id: str,
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
        use_hashkey: bool,
        max_attempts: int,
    ) -> dict[str, Any]:
        url = f"{self.settings.base_url}{path}"
        headers = self._build_headers(tr_id=tr_id)

        if use_hashkey:
            if json_body is None:
                raise RuntimeError("hashkey requested but json_body is None.")
            headers["hashkey"] = self.create_hashkey(json_body)

        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                self._throttle()

                self.logger.info(
                    "API request start. method=%s path=%s tr_id=%s attempt=%s",
                    method,
                    path,
                    tr_id,
                    attempt,
                )

                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=self.settings.request_timeout_seconds,
                )

                self._mark_request_time()

                response.raise_for_status()
                data = response.json()

                self._log_api_response_status(data=data, path=path, tr_id=tr_id)

                return data

            except requests.Timeout as exc:
                self._mark_request_time()
                last_error = exc
                self.logger.warning(
                    "API request timeout. method=%s path=%s tr_id=%s attempt=%s",
                    method,
                    path,
                    tr_id,
                    attempt,
                )

            except requests.RequestException as exc:
                self._mark_request_time()
                last_error = exc
                response = getattr(exc, "response", None)
                if response is not None:
                    self.logger.warning(
                        "API request failed. method=%s path=%s tr_id=%s attempt=%s status=%s response=%s",
                        method,
                        path,
                        tr_id,
                        attempt,
                        response.status_code,
                        response.text,
                    )
                else:
                    self.logger.warning(
                        "API request failed. method=%s path=%s tr_id=%s attempt=%s error=%s",
                        method,
                        path,
                        tr_id,
                        attempt,
                        exc,
                    )

            except ValueError as exc:
                self._mark_request_time()
                last_error = exc
                self.logger.warning(
                    "Failed to parse API response as JSON. path=%s tr_id=%s attempt=%s",
                    path,
                    tr_id,
                    attempt,
                )

            if attempt < max_attempts:
                sleep_seconds = max(3.0, 1.5 * attempt)
                self.logger.info("Retrying after %.1f seconds.", sleep_seconds)
                time.sleep(sleep_seconds)

        raise RuntimeError(
            f"API request failed after retries. method={method}, path={path}, tr_id={tr_id}"
        ) from last_error

    def create_hashkey(self, body: dict[str, Any]) -> str:
        """
        Create hashkey for POST order requests.

        Hashkey request itself is also an API request.
        Therefore, throttling is applied before and after this request.
        """

        url = f"{self.settings.base_url}/uapi/hashkey"

        headers = {
            "content-type": "application/json; charset=utf-8",
            "appkey": self.settings.app_key,
            "appsecret": self.settings.app_secret,
        }

        try:
            self._throttle()

            response = requests.post(
                url=url,
                headers=headers,
                json=body,
                timeout=self.settings.request_timeout_seconds,
            )

            self._mark_request_time()

            response.raise_for_status()
            data = response.json()

        except requests.RequestException as exc:
            self._mark_request_time()
            response = getattr(exc, "response", None)
            if response is not None:
                self.logger.error(
                    "Hashkey request failed. status=%s response=%s",
                    response.status_code,
                    response.text,
                )
            else:
                self.logger.error("Hashkey request failed. error=%s", exc)
            raise RuntimeError("Hashkey request failed.") from exc

        hashkey = data.get("HASH") or data.get("hash")
        if not hashkey:
            raise RuntimeError(f"Hashkey response does not contain HASH: {data}")

        self.logger.info("Hashkey created successfully.")
        return str(hashkey)

    def _build_headers(self, tr_id: str) -> dict[str, str]:
        access_token = self.auth_manager.get_access_token()

        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": self.settings.app_key,
            "appsecret": self.settings.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def _throttle(self) -> None:
        """
        Sleep if the previous API request was too recent.

        This is important because the mock trading environment has strict
        per-second request limits.
        """

        if self._last_request_time is None:
            return

        elapsed = time.monotonic() - self._last_request_time
        min_interval = self.settings.api_min_interval_seconds

        if elapsed < min_interval:
            sleep_seconds = min_interval - elapsed
            self.logger.info(
                "Throttling API request for %.2f seconds to avoid rate limit.",
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    def _mark_request_time(self) -> None:
        self._last_request_time = time.monotonic()

    def _log_api_response_status(
        self,
        data: dict[str, Any],
        path: str,
        tr_id: str,
    ) -> None:
        rt_cd = data.get("rt_cd")
        msg_cd = data.get("msg_cd")
        msg1 = data.get("msg1")

        if rt_cd is not None:
            if str(rt_cd) == "0":
                self.logger.info(
                    "API response success. path=%s tr_id=%s rt_cd=%s msg_cd=%s msg=%s",
                    path,
                    tr_id,
                    rt_cd,
                    msg_cd,
                    msg1,
                )
            else:
                self.logger.warning(
                    "API response returned non-success code. path=%s tr_id=%s rt_cd=%s msg_cd=%s msg=%s",
                    path,
                    tr_id,
                    rt_cd,
                    msg_cd,
                    msg1,
                )
        else:
            self.logger.info(
                "API response received. path=%s tr_id=%s response_keys=%s",
                path,
                tr_id,
                list(data.keys()),
            )
