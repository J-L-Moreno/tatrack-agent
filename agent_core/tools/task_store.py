"""DynamoDB-backed task storage used by the agent tools.

Table layout: partition key `actor_id`, sort key `task_id`. Every operation is
scoped to one actor, so a student can never read or modify someone else's tasks.
"""
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

STATUSES = ("todo", "in_progress", "blocked", "done")
PRIORITIES = ("low", "medium", "high", "urgent")
_PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_TAGS = 10
MAX_TAG_LENGTH = 30
_ID_ATTEMPTS = 3


class TaskValidationError(ValueError):
    pass


class TaskNotFoundError(LookupError):
    pass


class DynamoTable(Protocol):
    def put_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def delete_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def query(self, **kwargs: Any) -> dict[str, Any]: ...


def _clean_title(title: str | None) -> str:
    title = (title or "").strip()
    if not title:
        raise TaskValidationError("title is required.")
    if len(title) > MAX_TITLE_LENGTH:
        raise TaskValidationError(f"title must be at most {MAX_TITLE_LENGTH} characters.")
    return title


def _clean_description(description: str) -> str:
    description = description.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise TaskValidationError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters.")
    return description


def _clean_status(status: str) -> str:
    if status not in STATUSES:
        raise TaskValidationError(f"status must be one of: {', '.join(STATUSES)}.")
    return status


def _clean_priority(priority: str) -> str:
    if priority not in PRIORITIES:
        raise TaskValidationError(f"priority must be one of: {', '.join(PRIORITIES)}.")
    return priority


def _clean_date(value: str, field: str) -> str:
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except (AttributeError, ValueError):
        raise TaskValidationError(f"{field} must be a date in YYYY-MM-DD format.") from None


def _clean_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for tag in tags or []:
        tag = str(tag).strip().lower().replace(" ", "-")
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise TaskValidationError(f"each tag must be at most {MAX_TAG_LENGTH} characters.")
        if tag not in cleaned:
            cleaned.append(tag)
    if len(cleaned) > MAX_TAGS:
        raise TaskValidationError(f"a task can have at most {MAX_TAGS} tags.")
    return cleaned


def _is_conditional_failure(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _is_overdue(task: dict, today: str) -> bool:
    due = task.get("due_date")
    return task["status"] != "done" and bool(due) and due < today


def _sort_key(task: dict) -> tuple:
    return (
        task.get("due_date") or "9999-12-31",
        _PRIORITY_RANK.get(task.get("priority", ""), 9),
        task.get("created_at", ""),
    )


def _brief(task: dict) -> dict:
    return {key: task.get(key) for key in ("task_id", "title", "status", "priority", "due_date")}


class TaskStore:
    def __init__(
        self,
        table: DynamoTable,
        timezone_name: str = "UTC",
        clock: Callable[[], datetime] | None = None,
    ):
        self._table = table
        self._tz = ZoneInfo(timezone_name)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def today(self) -> date:
        """Today's date in the user's timezone (due dates are local dates)."""
        return self._clock().astimezone(self._tz).date()

    def _now_iso(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def _local_date(self, iso_timestamp: str) -> str:
        return datetime.fromisoformat(iso_timestamp).astimezone(self._tz).date().isoformat()

    # ── Create ─────────────────────────────────────────────────────────────

    def _build_item(
        self,
        actor_id: str,
        title: str,
        description: str | None = None,
        due_date: str | None = None,
        priority: str = "medium",
        tags: list[str] | None = None,
        status: str = "todo",
    ) -> dict:
        now = self._now_iso()
        item = {
            "actor_id": actor_id,
            "title": _clean_title(title),
            "status": _clean_status(status),
            "priority": _clean_priority(priority),
            "tags": _clean_tags(tags),
            "created_at": now,
            "updated_at": now,
        }
        if description and description.strip():
            item["description"] = _clean_description(description)
        if due_date and due_date.strip():
            item["due_date"] = _clean_date(due_date, "due_date")
        if item["status"] == "done":
            item["completed_at"] = now
        return item

    def _insert(self, item: dict) -> dict:
        for _ in range(_ID_ATTEMPTS):
            item["task_id"] = f"T-{secrets.token_hex(4)}"
            try:
                self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(task_id)")
                return item
            except ClientError as error:
                if not _is_conditional_failure(error):
                    raise
        raise RuntimeError("Could not allocate a unique task_id.")

    def create(self, actor_id: str, title: str, **fields: Any) -> dict:
        return self._insert(self._build_item(actor_id, title, **fields))

    def create_many(self, actor_id: str, specs: list[dict]) -> list[dict]:
        """Validate every task first so an invalid entry never leaves a partial batch behind."""
        items = [self._build_item(actor_id, **spec) for spec in specs]
        return [self._insert(item) for item in items]

    # ── Read ───────────────────────────────────────────────────────────────

    def get(self, actor_id: str, task_id: str) -> dict | None:
        return self._table.get_item(Key={"actor_id": actor_id, "task_id": task_id}).get("Item")

    def _require(self, actor_id: str, task_id: str) -> dict:
        task = self.get(actor_id, task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found.")
        return task

    def _all_tasks(self, actor_id: str) -> list[dict]:
        items: list[dict] = []
        kwargs: dict[str, Any] = {"KeyConditionExpression": Key("actor_id").eq(actor_id)}
        while True:
            page = self._table.query(**kwargs)
            items.extend(page.get("Items", []))
            last_key = page.get("LastEvaluatedKey")
            if not last_key:
                return items
            kwargs["ExclusiveStartKey"] = last_key

    def find(
        self,
        actor_id: str,
        *,
        statuses: list[str] | None = None,
        priority: str | None = None,
        tag: str | None = None,
        due_before: str | None = None,
        due_after: str | None = None,
        overdue_only: bool = False,
        completed_after: str | None = None,
        text: str | None = None,
    ) -> list[dict]:
        """Return matching tasks sorted by due date, then priority. Date bounds are inclusive."""
        wanted_statuses = {_clean_status(status) for status in statuses} if statuses else None
        priority = _clean_priority(priority) if priority else None
        tags = _clean_tags([tag]) if tag else []
        wanted_tag = tags[0] if tags else None
        due_before = _clean_date(due_before, "due_before") if due_before else None
        due_after = _clean_date(due_after, "due_after") if due_after else None
        completed_after = _clean_date(completed_after, "completed_after") if completed_after else None
        needle = text.strip().lower() if text and text.strip() else None
        today = self.today().isoformat()

        def matches(task: dict) -> bool:
            due = task.get("due_date")
            completed_at = task.get("completed_at")
            if wanted_statuses and task["status"] not in wanted_statuses:
                return False
            if priority and task["priority"] != priority:
                return False
            if wanted_tag and wanted_tag not in task.get("tags", []):
                return False
            if due_before and (not due or due > due_before):
                return False
            if due_after and (not due or due < due_after):
                return False
            if overdue_only and not _is_overdue(task, today):
                return False
            if completed_after and (not completed_at or self._local_date(completed_at) < completed_after):
                return False
            if needle and needle not in f"{task['title']} {task.get('description', '')}".lower():
                return False
            return True

        return sorted(filter(matches, self._all_tasks(actor_id)), key=_sort_key)

    # ── Update / Delete ────────────────────────────────────────────────────

    def update(
        self,
        actor_id: str,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        due_date: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Apply a partial update. An empty string clears description/due_date; an empty list clears tags."""
        if all(value is None for value in (title, description, status, due_date, priority, tags)):
            raise TaskValidationError("Provide at least one field to update.")

        current = self._require(actor_id, task_id)
        updated = dict(current)
        now = self._now_iso()

        if title is not None:
            updated["title"] = _clean_title(title)
        if description is not None:
            if description.strip():
                updated["description"] = _clean_description(description)
            else:
                updated.pop("description", None)
        if due_date is not None:
            if due_date.strip():
                updated["due_date"] = _clean_date(due_date, "due_date")
            else:
                updated.pop("due_date", None)
        if priority is not None:
            updated["priority"] = _clean_priority(priority)
        if tags is not None:
            updated["tags"] = _clean_tags(tags)
        if status is not None:
            updated["status"] = _clean_status(status)
            if updated["status"] == "done" and current["status"] != "done":
                updated["completed_at"] = now
            elif updated["status"] != "done":
                updated.pop("completed_at", None)

        updated["updated_at"] = now
        try:
            self._table.put_item(Item=updated, ConditionExpression="attribute_exists(task_id)")
        except ClientError as error:
            if _is_conditional_failure(error):
                raise TaskNotFoundError(f"Task {task_id} not found.") from None
            raise
        return updated

    def delete(self, actor_id: str, task_id: str) -> dict:
        try:
            response = self._table.delete_item(
                Key={"actor_id": actor_id, "task_id": task_id},
                ConditionExpression="attribute_exists(task_id)",
                ReturnValues="ALL_OLD",
            )
        except ClientError as error:
            if _is_conditional_failure(error):
                raise TaskNotFoundError(f"Task {task_id} not found.") from None
            raise
        return response.get("Attributes", {})

    # ── Progress ───────────────────────────────────────────────────────────

    def summarize(self, actor_id: str, *, tag: str | None = None, upcoming_days: int = 7) -> dict:
        if not 1 <= upcoming_days <= 60:
            raise TaskValidationError("upcoming_days must be between 1 and 60.")

        tasks = self.find(actor_id, tag=tag)
        today = self.today()
        today_iso = today.isoformat()
        horizon = (today + timedelta(days=upcoming_days)).isoformat()
        week_start = (today - timedelta(days=6)).isoformat()

        by_status = {status: 0 for status in STATUSES}
        open_by_priority = {priority: 0 for priority in PRIORITIES}
        overdue: list[dict] = []
        due_soon: list[dict] = []
        completed_last_7_days = 0

        for task in tasks:
            by_status[task["status"]] += 1
            if task["status"] == "done":
                completed_at = task.get("completed_at")
                if completed_at and self._local_date(completed_at) >= week_start:
                    completed_last_7_days += 1
                continue
            open_by_priority[task["priority"]] += 1
            due = task.get("due_date")
            if due and due < today_iso:
                overdue.append(_brief(task))
            elif due and due <= horizon:
                due_soon.append(_brief(task))

        total = len(tasks)
        return {
            "today": today_iso,
            "tag": tag,
            "total": total,
            "by_status": by_status,
            "open_by_priority": open_by_priority,
            "completion_rate_pct": round(100 * by_status["done"] / total, 1) if total else 0.0,
            "completed_last_7_days": completed_last_7_days,
            "overdue": overdue,
            "due_soon": due_soon,
            "upcoming_days": upcoming_days,
        }
