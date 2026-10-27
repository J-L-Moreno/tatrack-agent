import asyncio
import uuid

from langchain_core.messages import HumanMessage
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agent_factory import create_task_agent
from config import config
from response_tracker import update_response
from utils import extract_text_from_chunk, ThinkTagFilter

agent = create_task_agent(config)
app = BedrockAgentCoreApp()
TIMEOUT_MESSAGE = "La solicitud superó el tiempo máximo de ejecución del agente."
INACTIVITY_TIMEOUT_MESSAGE = "La solicitud se detuvo porque el agente dejó de responder."
ERROR_MESSAGE = "Ocurrió un error al procesar tu solicitud. Intenta de nuevo en unos momentos."
MISSING_FIELDS_MESSAGE = "La solicitud debe incluir 'prompt' y 'actor_id'."


class AgentInactivityTimeoutError(TimeoutError):
    pass


def build_invoke_config(payload: dict, context=None) -> dict:
    """Map the request payload to the LangGraph run config read by tools and middlewares."""
    session_id = payload.get("session_id") or getattr(context, "session_id", None) or str(uuid.uuid4())
    return {
        "configurable": {
            "thread_id": session_id,
            "actor_id": payload.get("actor_id"),
            # Scheduled reminder prompts must not become long-term memories.
            "memory_write": payload.get("source", "chat") != "reminder",
        },
        "recursion_limit": config.recursion_limit,
    }


async def _next_stream_part(stream):
    inactivity_timeout = asyncio.timeout(config.agent_inactivity_timeout_sec)
    try:
        async with inactivity_timeout:
            return await anext(stream)
    except TimeoutError as error:
        if inactivity_timeout.expired():
            raise AgentInactivityTimeoutError from error
        raise


async def _invoke_with_inactivity_timeout(user_input, invoke_config):
    """Run the agent to completion while enforcing inactivity between events."""
    result = {}
    stream = agent.astream(
        {"messages": [HumanMessage(content=user_input)]},
        config=invoke_config,
        stream_mode=["messages", "values"],
        version="v2",
    ).__aiter__()

    while True:
        try:
            part = await _next_stream_part(stream)
        except StopAsyncIteration:
            break

        if part.get("type") == "values" and isinstance(part.get("data"), dict):
            result = part["data"]

    return result


@app.entrypoint
async def invoke(payload, context=None):
    """
    Invoke the agent with a payload.
    - streaming=True: returns an async generator (text/event-stream)
    - streaming=False: returns a plain string (single response)
    """
    user_input = payload.get("prompt")
    streaming = str(payload.get("streaming", False)).lower() == "true"
    response_id = payload.get("response_id")
    invoke_config = build_invoke_config(payload, context)
    configurable = invoke_config["configurable"]

    print(
        f"session_id={configurable['thread_id']} actor_id={configurable['actor_id']} "
        f"source={payload.get('source', 'chat')} streaming={streaming} response_id={response_id}"
    )

    if not user_input or not configurable["actor_id"]:
        update_response(response_id, "FAILED", MISSING_FIELDS_MESSAGE)
        return MISSING_FIELDS_MESSAGE

    if streaming:
        return _stream_response(user_input, invoke_config)

    try:
        async with asyncio.timeout(config.agent_request_timeout_sec):
            result = await _invoke_with_inactivity_timeout(user_input, invoke_config)
        messages = result.get("messages", [])
        response = extract_text_from_chunk(messages[-1]) if messages else ""
        update_response(response_id, "COMPLETED", response)
        return response
    except AgentInactivityTimeoutError:
        update_response(response_id, "FAILED", INACTIVITY_TIMEOUT_MESSAGE)
        return INACTIVITY_TIMEOUT_MESSAGE
    except TimeoutError:
        update_response(response_id, "FAILED", TIMEOUT_MESSAGE)
        return TIMEOUT_MESSAGE
    except Exception as e:
        print(f"Agent error: {e!r}")
        update_response(response_id, "FAILED", ERROR_MESSAGE)
        return ERROR_MESSAGE


async def _stream_response(user_input, invoke_config):
    """Async generator that yields text chunks for streaming mode."""
    yielded = False
    think_filter = ThinkTagFilter()
    try:
        async with asyncio.timeout(config.agent_request_timeout_sec):
            stream = agent.astream(
                {"messages": [HumanMessage(content=user_input)]},
                config=invoke_config,
                stream_mode=["messages", "values"],
                version="v2",
            ).__aiter__()
            while True:
                try:
                    part = await _next_stream_part(stream)
                except StopAsyncIteration:
                    break

                if part.get("type") != "messages" or not isinstance(part.get("data"), tuple):
                    continue
                message, metadata = part["data"]
                if metadata.get("langgraph_node") != "model":
                    continue
                text = extract_text_from_chunk(message)
                if text:
                    filtered = think_filter.feed(text)
                    if filtered:
                        yielded = True
                        yield filtered

        # Flush any buffered partial-tag text at end of stream
        remaining = think_filter.flush()
        if remaining:
            yield remaining

    except AgentInactivityTimeoutError:
        prefix = "\n\n" if yielded else ""
        yield prefix + INACTIVITY_TIMEOUT_MESSAGE
    except TimeoutError:
        prefix = "\n\n" if yielded else ""
        yield prefix + TIMEOUT_MESSAGE
    except Exception as e:
        print(f"Agent stream error: {e!r}")
        prefix = "\n\n" if yielded else ""
        yield prefix + ERROR_MESSAGE


if __name__ == "__main__":
    app.run()
