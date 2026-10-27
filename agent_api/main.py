from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app_logging import get_logger
from constants import ACTOR_ID_PATTERN, MAX_TAG_LENGTH, STREAMING_RESPONSE_HEADERS, TASK_ID_PATTERN
from dependencies import (
    get_config,
    get_message_service,
    get_response_repository,
    get_task_repository,
    require_api_key,
)
from repositories import ResponseRepository, TaskRepository
from schemas import ChatRequest, TaskPriority, TaskStatus
from services import MessageService


logger = get_logger()
config = get_config()

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Task Tracker Agent API")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"rate_limit_exceeded ip={get_remote_address(request)} path={request.url.path}")
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."})


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception):
    logger.error(f"unhandled_error path={request.url.path} error={exc!r}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ── Endpoints ───────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/messages")
@limiter.limit(config.rate_limit)
async def create_message(
    request: Request,
    body: ChatRequest,
    _key: str = Depends(require_api_key),
    message_service: MessageService = Depends(get_message_service),
):
    prepared_request = message_service.prepare_request(body)

    if prepared_request.streaming:
        return StreamingResponse(
            message_service.stream_message(prepared_request),
            media_type="text/event-stream",
            headers=STREAMING_RESPONSE_HEADERS,
        )

    result = await message_service.create_sync_message(prepared_request)
    return JSONResponse(status_code=result.status_code, content=result.payload)


@app.get("/responses/{response_id}")
@limiter.limit(config.rate_limit)
async def get_response(
    request: Request,
    response_id: str = Path(max_length=64),
    _key: str = Depends(require_api_key),
    repository: ResponseRepository = Depends(get_response_repository),
):
    item = repository.get_response(response_id)
    if not item:
        raise HTTPException(status_code=404, detail="Response not found")

    return {
        "response_id": item.get("id", response_id),
        "status": item.get("status", "unknown"),
        "response": item.get("response", ""),
    }


@app.get("/tasks")
@limiter.limit(config.rate_limit)
async def list_tasks(
    request: Request,
    actor_id: str = Query(pattern=ACTOR_ID_PATTERN),
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    tag: str | None = Query(default=None, min_length=1, max_length=MAX_TAG_LENGTH),
    _key: str = Depends(require_api_key),
    repository: TaskRepository = Depends(get_task_repository),
):
    tasks = repository.list_tasks(actor_id, status=status, priority=priority, tag=tag.lower() if tag else None)
    return {"count": len(tasks), "tasks": tasks}


@app.get("/tasks/{task_id}")
@limiter.limit(config.rate_limit)
async def get_task(
    request: Request,
    task_id: str = Path(pattern=TASK_ID_PATTERN),
    actor_id: str = Query(pattern=ACTOR_ID_PATTERN),
    _key: str = Depends(require_api_key),
    repository: TaskRepository = Depends(get_task_repository),
):
    task = repository.get_task(actor_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
