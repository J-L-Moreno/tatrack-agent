from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from constants import ACTOR_ID_PATTERN, MAX_PROMPT_LENGTH, SESSION_ID_PATTERN

TaskStatus = Literal["todo", "in_progress", "blocked", "done"]
TaskPriority = Literal["low", "medium", "high", "urgent"]


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    actor_id: str = Field(pattern=ACTOR_ID_PATTERN)
    streaming: bool = False


@dataclass(frozen=True)
class PreparedAgentRequest:
    payload: bytes
    response_id: str | None
    streaming: bool


@dataclass(frozen=True)
class ServiceResult:
    status_code: int
    payload: dict
