import os
from dataclasses import dataclass

from botocore.config import Config


@dataclass(frozen=True)
class AppConfig:
    allowed_origins: list[str]
    agent_runtime_arn: str | None
    api_keys_secret_name: str | None
    api_keys_cache_ttl: float
    dynamodb_table_name: str | None
    tasks_table_name: str | None
    rate_limit: str
    stream_keepalive_interval: int
    sync_response_timeout_seconds: float
    response_ttl_seconds: int


def load_config() -> AppConfig:
    return AppConfig(
        allowed_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
        agent_runtime_arn=os.getenv("AGENT_RUNTIME_ARN"),
        api_keys_secret_name=os.getenv("API_KEYS_SECRET_NAME"),
        api_keys_cache_ttl=float(os.getenv("API_KEYS_CACHE_TTL", "300")),
        dynamodb_table_name=os.getenv("DYNAMODB_TABLE_NAME"),
        tasks_table_name=os.getenv("TASKS_TABLE_NAME"),
        rate_limit=os.getenv("RATE_LIMIT", "10/minute"),
        stream_keepalive_interval=int(os.getenv("STREAM_KEEPALIVE_INTERVAL", "25")),
        sync_response_timeout_seconds=float(os.getenv("SYNC_RESPONSE_TIMEOUT_SECONDS", "50")),
        response_ttl_seconds=int(os.getenv("RESPONSE_TTL_SECONDS", str(7 * 24 * 3600))),
    )


def build_boto_config() -> Config:
    return Config(
        read_timeout=600,
        connect_timeout=60,
        retries={"max_attempts": 3},
    )
