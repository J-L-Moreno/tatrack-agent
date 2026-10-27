from botocore.config import Config
from langchain.agents import create_agent
from langchain_aws import ChatBedrockConverse
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_checkpoint_aws import AgentCoreMemorySaver, AgentCoreMemoryStore

from config import AgentConfig
from middlewares import MemoryMiddleware, SkillMiddleware
from prompts import build_system_prompt
from tool_registry import get_tools


def create_task_agent(cfg: AgentConfig):
    """Create and return the configured task tracker agent."""
    boto_config = Config(
        read_timeout=cfg.boto_read_timeout,
        connect_timeout=cfg.boto_connect_timeout,
        retries={'max_attempts': cfg.boto_max_retries}
    )

    temperature = cfg.model_temperature
    model_kwargs = {}
    if "anthropic" in cfg.bedrock_model_id:
        model_kwargs["additional_model_request_fields"] = {
            "thinking": {"type": "adaptive"}
        }
        # Adaptive thinking rejects any other value.
        temperature = 1.0

    # langchain_aws doesn't recognize moonshot as a streaming-capable provider,
    # but Bedrock ConverseStream does support it. Force streaming enabled.
    if "moonshot" in cfg.bedrock_model_id:
        model_kwargs["disable_streaming"] = False

    model = ChatBedrockConverse(
        model=cfg.bedrock_model_id,
        region_name=cfg.aws_region,
        max_tokens=cfg.model_max_tokens,
        temperature=temperature,
        config=boto_config,
        **model_kwargs,
    )

    # Short-term memory (conversation history per session_id). In-memory when running without AgentCore.
    checkpointer = (
        AgentCoreMemorySaver(cfg.bedrock_agentcore_memory_id, region_name=cfg.aws_region)
        if cfg.bedrock_agentcore_memory_id
        else InMemorySaver()
    )

    # Long-term memory (USER_PREFERENCE + SEMANTIC strategies) shared across sessions of the same actor.
    use_long_term_memory = cfg.enable_long_term_memory and bool(cfg.bedrock_agentcore_memory_id)
    store = (
        AgentCoreMemoryStore(memory_id=cfg.bedrock_agentcore_memory_id, region_name=cfg.aws_region)
        if use_long_term_memory
        else None
    )

    middlewares = [SkillMiddleware()]
    if use_long_term_memory:
        middlewares.append(
            MemoryMiddleware(
                namespace_prefix=cfg.memory_namespace_prefix,
                search_limit=cfg.memory_search_limit,
            )
        )

    return create_agent(
        model,
        get_tools(),
        system_prompt=build_system_prompt(cfg),
        checkpointer=checkpointer,
        store=store,
        middleware=middlewares,
    )
