import os
from dataclasses import dataclass, field


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value or str(default))


def _get_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value or str(default))


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() == "true"


@dataclass(frozen=True)
class AgentConfig:
    # --- AWS / Agent Identity ---
    agent_name: str = field(default_factory=lambda: os.getenv("TASK_AGENT_NAME", "task_agent"))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))

    # --- DynamoDB ---
    tasks_table_name: str = field(default_factory=lambda: os.getenv("TASKS_TABLE_NAME", ""))
    # Response tracking table used by the API for synchronous requests.
    dynamodb_table_name: str = field(default_factory=lambda: os.getenv("DYNAMODB_TABLE_NAME", ""))

    # --- User context ---
    user_timezone: str = field(default_factory=lambda: os.getenv("USER_TIMEZONE", "UTC"))

    # --- Bedrock / Model ---
    bedrock_model_id: str = field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", "moonshotai.kimi-k2.5"))
    model_temperature: float = field(default_factory=lambda: _get_float_env("MODEL_TEMPERATURE", 0.2))
    model_max_tokens: int = field(default_factory=lambda: _get_int_env("MODEL_MAX_TOKENS", 8192))
    agent_request_timeout_sec: int = field(default_factory=lambda: _get_int_env("AGENT_REQUEST_TIMEOUT_SEC", 300))
    agent_inactivity_timeout_sec: int = field(
        default_factory=lambda: _get_int_env("AGENT_INACTIVITY_TIMEOUT_SEC", 120)
    )
    recursion_limit: int = field(default_factory=lambda: _get_int_env("RECURSION_LIMIT", 50))

    # --- AgentCore Memory ---
    bedrock_agentcore_memory_id: str = field(default_factory=lambda: os.getenv("BEDROCK_AGENTCORE_MEMORY_ID", ""))
    enable_long_term_memory: bool = field(default_factory=lambda: _get_bool_env("ENABLE_LONG_TERM_MEMORY", True))
    # Must match the strategy namespaces created by Terraform: /<prefix>/user/{actorId}/(semantic|preferences)/
    memory_namespace_prefix: str = field(default_factory=lambda: os.getenv("MEMORY_NAMESPACE_PREFIX", "tasks"))
    memory_search_limit: int = field(default_factory=lambda: _get_int_env("MEMORY_SEARCH_LIMIT", 5))

    # --- Boto3 ---
    boto_read_timeout: int = 300
    boto_connect_timeout: int = 60
    boto_max_retries: int = 3


config = AgentConfig()
