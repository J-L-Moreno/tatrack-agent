"""Task tools exposed to the agent.

The actor_id is read from the run config (set by main.py from the API request), never
from a tool argument, so the model cannot read or modify another student's tasks.
"""
import json
from collections.abc import Callable
from functools import lru_cache
from typing import Any, Literal

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool
from langgraph.config import get_config
from pydantic import BaseModel, Field

from config import config
from tools.task_store import TaskNotFoundError, TaskStore, TaskValidationError

Status = Literal["todo", "in_progress", "blocked", "done"]
Priority = Literal["low", "medium", "high", "urgent"]

MAX_BULK_TASKS = 15
MAX_LIST_LIMIT = 100


class NewTask(BaseModel):
    title: str = Field(description="Short, actionable title (max 200 characters).")
    description: str | None = Field(default=None, description="Optional details (max 2000 characters).")
    due_date: str | None = Field(default=None, description="Optional due date in YYYY-MM-DD format.")
    priority: Priority = Field(default="medium", description="low, medium, high or urgent.")
    tags: list[str] | None = Field(default=None, description="Optional list of up to 10 lowercase tags.")
    status: Status = Field(default="todo", description="Initial status.")


@lru_cache
def get_task_store() -> TaskStore:
    table = boto3.resource("dynamodb", region_name=config.aws_region).Table(config.tasks_table_name)
    return TaskStore(table, timezone_name=config.user_timezone)


def _actor_id() -> str:
    actor_id = get_config().get("configurable", {}).get("actor_id")
    if not actor_id:
        raise TaskValidationError("Missing actor_id in the request; tasks cannot be accessed.")
    return actor_id


def _public(task: dict) -> dict:
    return {key: value for key, value in task.items() if key != "actor_id"}


def _run(operation: Callable[[], dict[str, Any]]) -> str:
    """Execute a store operation and always answer the model with JSON (errors included)."""
    try:
        return json.dumps(operation(), ensure_ascii=False)
    except (TaskValidationError, TaskNotFoundError) as error:
        return json.dumps({"error": str(error)}, ensure_ascii=False)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "Unknown")
        return json.dumps({"error": f"Task storage error ({code}). Try again later."})


@tool(parse_docstring=True)
def create_task(
    title: str,
    description: str | None = None,
    due_date: str | None = None,
    priority: Priority = "medium",
    tags: list[str] | None = None,
    status: Status = "todo",
) -> str:
    """Create a new task for the current user.

    Args:
        title: Short, actionable title (max 200 characters).
        description: Optional details (max 2000 characters).
        due_date: Optional due date in YYYY-MM-DD format (user's local date).
        priority: low, medium, high or urgent.
        tags: Optional list of up to 10 short lowercase tags.
        status: Initial status: todo, in_progress, blocked or done.
    """
    def operation() -> dict:
        task = get_task_store().create(
            _actor_id(),
            title,
            description=description,
            due_date=due_date,
            priority=priority,
            tags=tags,
            status=status,
        )
        return {"created": _public(task)}

    return _run(operation)


@tool(parse_docstring=True)
def create_tasks_bulk(tasks: list[NewTask]) -> str:
    """Create several tasks at once (for example after breaking a goal into steps).

    All tasks are validated before any is saved: if one is invalid, none is created.

    Args:
        tasks: Between 1 and 15 tasks to create.
    """
    def operation() -> dict:
        if not 1 <= len(tasks) <= MAX_BULK_TASKS:
            raise TaskValidationError(f"Provide between 1 and {MAX_BULK_TASKS} tasks per call.")
        specs = [NewTask.model_validate(task).model_dump() for task in tasks]
        created = get_task_store().create_many(_actor_id(), specs)
        return {"created": [_public(task) for task in created]}

    return _run(operation)


@tool(parse_docstring=True)
def get_task(task_id: str) -> str:
    """Get one task by its ID.

    Args:
        task_id: Task ID returned by other tools (format T-xxxxxxxx).
    """
    def operation() -> dict:
        task = get_task_store().get(_actor_id(), task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found.")
        return {"task": _public(task)}

    return _run(operation)


@tool(parse_docstring=True)
def list_tasks(
    status: list[Status] | None = None,
    priority: Priority | None = None,
    tag: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    overdue_only: bool = False,
    completed_after: str | None = None,
    text: str | None = None,
    limit: int = 50,
) -> str:
    """List the user's tasks with optional filters, sorted by due date and priority.

    Use `text` to find a task the user mentions by name. Date bounds are inclusive.

    Args:
        status: Only tasks in any of these statuses.
        priority: Only tasks with this priority.
        tag: Only tasks with this tag.
        due_before: Only tasks due on or before this date (YYYY-MM-DD).
        due_after: Only tasks due on or after this date (YYYY-MM-DD).
        overdue_only: Only open tasks whose due date is before today.
        completed_after: Only tasks completed on or after this local date (YYYY-MM-DD).
        text: Case-insensitive search in title and description.
        limit: Maximum number of tasks to return (1-100).
    """
    def operation() -> dict:
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise TaskValidationError(f"limit must be between 1 and {MAX_LIST_LIMIT}.")
        store = get_task_store()
        matches = store.find(
            _actor_id(),
            statuses=status,
            priority=priority,
            tag=tag,
            due_before=due_before,
            due_after=due_after,
            overdue_only=overdue_only,
            completed_after=completed_after,
            text=text,
        )
        return {
            "today": store.today().isoformat(),
            "total_matches": len(matches),
            "returned": min(len(matches), limit),
            "tasks": [_public(task) for task in matches[:limit]],
        }

    return _run(operation)


@tool(parse_docstring=True)
def update_task(
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: Status | None = None,
    due_date: str | None = None,
    priority: Priority | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update one or more fields of an existing task. Omitted fields stay unchanged.

    Args:
        task_id: ID of the task to update.
        title: New title.
        description: New description; an empty string removes it.
        status: New status. Setting done records the completion time.
        due_date: New due date (YYYY-MM-DD); an empty string removes it.
        priority: New priority.
        tags: Full replacement list of tags; an empty list removes all tags.
    """
    def operation() -> dict:
        task = get_task_store().update(
            _actor_id(),
            task_id,
            title=title,
            description=description,
            status=status,
            due_date=due_date,
            priority=priority,
            tags=tags,
        )
        return {"updated": _public(task)}

    return _run(operation)


@tool(parse_docstring=True)
def delete_task(task_id: str, confirmed: bool = False) -> str:
    """Permanently delete a task. Requires explicit user confirmation.

    First call it with confirmed=false: nothing is deleted and the task is returned so you
    can ask the user to confirm. Call it with confirmed=true only after the user explicitly
    confirms the deletion in a later message.

    Args:
        task_id: ID of the task to delete.
        confirmed: True only after the user explicitly confirmed this deletion.
    """
    def operation() -> dict:
        store = get_task_store()
        actor_id = _actor_id()
        if not confirmed:
            task = store.get(actor_id, task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found.")
            return {
                "status": "confirmation_required",
                "task": _public(task),
                "instructions": (
                    "Nothing was deleted. Show this task to the user and ask for explicit confirmation. "
                    "Call delete_task with confirmed=true only after the user confirms in a new message."
                ),
            }
        return {"status": "deleted", "task": _public(store.delete(actor_id, task_id))}

    return _run(operation)


@tool(parse_docstring=True)
def summarize_progress(tag: str | None = None, upcoming_days: int = 7) -> str:
    """Summarize the user's progress: counts by status, open tasks by priority, completion rate,
    tasks completed in the last 7 days, overdue tasks and tasks due soon.

    Args:
        tag: Optional tag to summarize only one course or project.
        upcoming_days: Window in days for "due soon" (1-60).
    """
    return _run(lambda: get_task_store().summarize(_actor_id(), tag=tag, upcoming_days=upcoming_days))


TASK_TOOLS = [
    create_task,
    create_tasks_bulk,
    get_task,
    list_tasks,
    update_task,
    delete_task,
    summarize_progress,
]
