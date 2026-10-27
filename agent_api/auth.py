import hmac
import os
import time
from collections.abc import Callable
from logging import Logger
from typing import Protocol

from fastapi import HTTPException


class SecretsManagerClient(Protocol):
    def get_secret_value(self, *, SecretId: str) -> dict: ...


class APIKeyProvider:
    def __init__(
        self,
        secrets_client: SecretsManagerClient,
        api_keys_secret_name: str | None,
        cache_ttl: float,
        logger: Logger,
        time_source: Callable[[], float] = time.time,
    ):
        self._secrets_client = secrets_client
        self._api_keys_secret_name = api_keys_secret_name
        self._cache_ttl = cache_ttl
        self._logger = logger
        self._time_source = time_source
        self._cache: set[str] | None = None
        self._last_fetched = 0.0

    def load_api_keys(self) -> set[str]:
        now = self._time_source()
        if self._cache is None or (now - self._last_fetched) > self._cache_ttl:
            try:
                if self._api_keys_secret_name:
                    response = self._secrets_client.get_secret_value(SecretId=self._api_keys_secret_name)
                    secret_string = response.get("SecretString", "")
                    self._cache = set(filter(None, (key.strip() for key in secret_string.split(","))))
                else:
                    self._cache = set(filter(None, (key.strip() for key in os.getenv("API_KEYS", "").split(","))))
                self._last_fetched = now
                self._logger.info("API keys cache refreshed")
            except Exception as exc:
                self._logger.error(f"Failed to refresh API keys: {exc}")
                if self._cache is None:
                    self._cache = set()

        return self._cache

    def validate(self, api_key: str) -> str:
        if not any(hmac.compare_digest(api_key, key) for key in self.load_api_keys()):
            raise HTTPException(status_code=403, detail="Invalid API key")
        return api_key
