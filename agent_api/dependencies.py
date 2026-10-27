from functools import lru_cache

import boto3
from fastapi import Depends, Header

from app_logging import get_logger
from auth import APIKeyProvider
from config import AppConfig, build_boto_config, load_config
from repositories import ResponseRepository, TaskRepository
from services import AgentRuntimeService, MessageService


@lru_cache
def get_config() -> AppConfig:
    return load_config()


@lru_cache
def get_bedrock_agentcore_client():
    return boto3.client("bedrock-agentcore", config=build_boto_config())


@lru_cache
def get_secretsmanager_client():
    return boto3.client("secretsmanager")


@lru_cache
def get_dynamodb_resource():
    return boto3.resource("dynamodb")


@lru_cache
def get_api_key_provider() -> APIKeyProvider:
    config = get_config()
    return APIKeyProvider(
        secrets_client=get_secretsmanager_client(),
        api_keys_secret_name=config.api_keys_secret_name,
        cache_ttl=config.api_keys_cache_ttl,
        logger=get_logger(),
    )


def require_api_key(
    x_api_key: str = Header(...),
    provider: APIKeyProvider = Depends(get_api_key_provider),
) -> str:
    return provider.validate(x_api_key)


def get_response_repository() -> ResponseRepository:
    config = get_config()
    return ResponseRepository(get_dynamodb_resource(), config.dynamodb_table_name, config.response_ttl_seconds)


def get_task_repository() -> TaskRepository:
    return TaskRepository(get_dynamodb_resource(), get_config().tasks_table_name)


def get_agent_runtime_service() -> AgentRuntimeService:
    config = get_config()
    return AgentRuntimeService(
        client=get_bedrock_agentcore_client(),
        agent_runtime_arn=config.agent_runtime_arn,
        stream_keepalive_interval=config.stream_keepalive_interval,
        sync_response_timeout_seconds=config.sync_response_timeout_seconds,
    )


def get_message_service(
    repository: ResponseRepository = Depends(get_response_repository),
    agent_runtime_service: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> MessageService:
    return MessageService(repository, agent_runtime_service, get_logger())
