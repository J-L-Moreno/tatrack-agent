import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from logging import Logger
from typing import Any, Protocol

from repositories import ResponseRepository
from schemas import ChatRequest, PreparedAgentRequest, ServiceResult


class AgentCoreClient(Protocol):
    def invoke_agent_runtime(self, *, agentRuntimeArn: str | None, payload: bytes) -> dict[str, Any]: ...


class AgentRuntimeService:
    def __init__(
        self,
        client: AgentCoreClient,
        agent_runtime_arn: str | None,
        stream_keepalive_interval: int,
        sync_response_timeout_seconds: float,
    ):
        self._client = client
        self._agent_runtime_arn = agent_runtime_arn
        self._stream_keepalive_interval = stream_keepalive_interval
        self._sync_response_timeout_seconds = sync_response_timeout_seconds

    @staticmethod
    def build_payload(body: ChatRequest, response_id: str | None) -> bytes:
        return json.dumps({
            "prompt": body.prompt,
            "session_id": body.session_id,
            "actor_id": body.actor_id,
            "streaming": body.streaming,
            "response_id": response_id,
            "source": "chat",
        }).encode("utf-8")

    async def stream_response(self, payload: bytes) -> AsyncIterator[str]:
        try:
            response = await asyncio.to_thread(self._invoke_agent, payload)
            queue: asyncio.Queue[str | None] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def _read() -> None:
                for text in self._extract_text_parts(response):
                    loop.call_soon_threadsafe(queue.put_nowait, text)
                loop.call_soon_threadsafe(queue.put_nowait, None)

            loop.run_in_executor(None, _read)

            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=self._stream_keepalive_interval)
                    if item is None:
                        break
                    yield f"data: {json.dumps({'chunk': item}, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"

            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': type(exc).__name__})}\n\n"

    async def invoke_sync_response(self, payload: bytes, response_id: str) -> ServiceResult:
        def _run() -> str:
            response = self._invoke_agent(payload)
            return self._decode_json_text("".join(self._extract_text_parts(response)))

        try:
            full_response = await asyncio.wait_for(
                asyncio.to_thread(_run),
                timeout=self._sync_response_timeout_seconds,
            )
            return ServiceResult(
                status_code=200,
                payload={"response_id": response_id, "status": "COMPLETED", "response": full_response},
            )
        except asyncio.TimeoutError:
            # The agent keeps running; the client polls GET /responses/{response_id}.
            return ServiceResult(
                status_code=202,
                payload={"response_id": response_id, "status": "IN-PROGRESS", "response": ""},
            )

    def _invoke_agent(self, payload: bytes) -> dict[str, Any]:
        return self._client.invoke_agent_runtime(
            agentRuntimeArn=self._agent_runtime_arn,
            payload=payload,
        )

    def _extract_text_parts(self, response: dict[str, Any]) -> Iterator[str]:
        content_type = response.get("contentType", "")
        if "text/event-stream" in content_type:
            for line in response["response"].iter_lines(chunk_size=10):
                if line:
                    text = self._parse_sse_data(line.decode("utf-8"))
                    if text:
                        yield text
            return

        for chunk in response.get("response", []):
            yield chunk.decode("utf-8")

    @staticmethod
    def _parse_sse_data(raw: str) -> str:
        if not raw.startswith("data: "):
            return ""
        data_line = raw[6:]
        try:
            parsed = json.loads(data_line)
            if isinstance(parsed, dict):
                return parsed.get("chunk", str(parsed))
            return str(parsed)
        except json.JSONDecodeError:
            return data_line

    @staticmethod
    def _decode_json_text(raw: str) -> str:
        """Non-streaming runtime responses are JSON-encoded strings."""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        return parsed if isinstance(parsed, str) else raw


class MessageService:
    def __init__(self, repository: ResponseRepository, agent_runtime_service: AgentRuntimeService, logger: Logger):
        self._repository = repository
        self._agent_runtime_service = agent_runtime_service
        self._logger = logger

    def prepare_request(self, body: ChatRequest) -> PreparedAgentRequest:
        response_id = None if body.streaming else str(uuid.uuid4())
        payload = self._agent_runtime_service.build_payload(body, response_id)
        self._logger.info(
            f"invoke session_id={body.session_id} actor_id={body.actor_id} "
            f"streaming={body.streaming} response_id={response_id}"
        )
        return PreparedAgentRequest(payload=payload, response_id=response_id, streaming=body.streaming)

    async def create_sync_message(self, prepared_request: PreparedAgentRequest) -> ServiceResult:
        if prepared_request.response_id is None:
            raise ValueError("Synchronous requests require a response_id")

        self._repository.create_pending_response(prepared_request.response_id)
        return await self._agent_runtime_service.invoke_sync_response(
            prepared_request.payload,
            prepared_request.response_id,
        )

    def stream_message(self, prepared_request: PreparedAgentRequest) -> AsyncIterator[str]:
        return self._agent_runtime_service.stream_response(prepared_request.payload)
