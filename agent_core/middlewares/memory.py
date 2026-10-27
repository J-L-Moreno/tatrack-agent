import uuid
from typing import Callable, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_config

# (label shown to the model, namespace suffix created by the Terraform memory strategy)
_MEMORY_KINDS = (
    ("Preferencias del usuario", "preferences"),
    ("Contexto de conversaciones anteriores", "semantic"),
)


class MemoryState(AgentState):
    long_term_memories: NotRequired[str]


def _message_text(message: HumanMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return " ".join(
        block.get("text", "") for block in message.content if isinstance(block, dict) and block.get("type") == "text"
    )


class MemoryMiddleware(AgentMiddleware[MemoryState]):
    """Long-term memory backed by AgentCore Memory (USER_PREFERENCE + SEMANTIC strategies).

    Before each turn: stores the user's message as a conversational event (the strategies
    extract preferences/facts from it asynchronously) and retrieves relevant records.
    Before each model call: appends the retrieved records to the system prompt. They live in
    graph state, not in the message history, so they don't pile up across turns.
    """

    state_schema = MemoryState

    def __init__(self, namespace_prefix: str = "tasks", search_limit: int = 5):
        super().__init__()
        self.namespace_prefix = namespace_prefix
        self.search_limit = search_limit

    def before_agent(self, state, runtime):
        store = runtime.store
        configurable = get_config().get("configurable", {})
        actor_id = configurable.get("actor_id")
        thread_id = configurable.get("thread_id")
        latest = next((m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None)
        query = _message_text(latest).strip() if latest else ""
        if store is None or not actor_id or not query:
            return {"long_term_memories": ""}

        # Reminder runs read preferences but must not turn the scheduler prompt into memories.
        if configurable.get("memory_write", True) and thread_id:
            try:
                store.put((actor_id, thread_id), str(uuid.uuid4()), {"message": latest})
            except Exception as e:
                print(f"[Memory] Put error: {e}")

        blocks = []
        for label, kind in _MEMORY_KINDS:
            try:
                items = store.search(
                    # The trailing "" renders as "/<prefix>/user/<actor>/<kind>/", matching the strategy template.
                    (self.namespace_prefix, "user", actor_id, kind, ""),
                    query=query,
                    limit=self.search_limit,
                )
            except Exception as e:
                print(f"[Memory] Search error ({kind}): {e}")
                continue
            lines = [f"- {content}" for item in items if (content := str(item.value.get("content", "")).strip())]
            if lines:
                blocks.append(f"### {label}\n" + "\n".join(lines))

        return {"long_term_memories": "\n\n".join(blocks)}

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._inject_memories(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return await handler(self._inject_memories(request))

    def _inject_memories(self, request: ModelRequest) -> ModelRequest:
        memories = request.state.get("long_term_memories")
        if not memories:
            return request

        addendum = (
            "\n\n## Memoria a largo plazo del usuario\n\n"
            f"{memories}\n\n"
            "Usa estas memorias solo para personalizar la respuesta. El estado real de las "
            "tareas siempre proviene de las herramientas."
        )
        new_content = list(request.system_message.content_blocks) + [{"type": "text", "text": addendum}]
        return request.override(system_message=SystemMessage(content=new_content))
