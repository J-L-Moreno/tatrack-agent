import time
from typing import Any, Protocol

from boto3.dynamodb.conditions import Key as DynamoKey

_PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}


class DynamoTable(Protocol):
    def put_item(self, *, Item: dict[str, Any]) -> dict[str, Any]: ...
    def get_item(self, *, Key: dict[str, Any]) -> dict[str, Any]: ...
    def query(self, **kwargs: Any) -> dict[str, Any]: ...


class DynamoResource(Protocol):
    def Table(self, name: str | None) -> DynamoTable: ...


class ResponseRepository:
    def __init__(self, dynamodb_resource: DynamoResource, table_name: str | None, ttl_seconds: int):
        self._table = dynamodb_resource.Table(table_name)
        self._ttl_seconds = ttl_seconds

    def create_pending_response(self, response_id: str) -> None:
        self._table.put_item(Item={
            "id": response_id,
            "response": "",
            "status": "IN-PROGRESS",
            "ttl": int(time.time()) + self._ttl_seconds,
        })

    def get_response(self, response_id: str) -> dict[str, Any] | None:
        result = self._table.get_item(Key={"id": response_id})
        return result.get("Item")


def _public(task: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in task.items() if key != "actor_id"}


class TaskRepository:
    """Read-only access to the tasks table (writes go through the agent tools)."""

    def __init__(self, dynamodb_resource: DynamoResource, table_name: str | None):
        self._table = dynamodb_resource.Table(table_name)

    def get_task(self, actor_id: str, task_id: str) -> dict[str, Any] | None:
        item = self._table.get_item(Key={"actor_id": actor_id, "task_id": task_id}).get("Item")
        return _public(item) if item else None

    def list_tasks(
        self,
        actor_id: str,
        status: str | None = None,
        priority: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {"KeyConditionExpression": DynamoKey("actor_id").eq(actor_id)}
        while True:
            page = self._table.query(**kwargs)
            items.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

        matches = [
            task for task in items
            if (status is None or task.get("status") == status)
            and (priority is None or task.get("priority") == priority)
            and (tag is None or tag in task.get("tags", []))
        ]
        matches.sort(key=lambda task: (
            task.get("due_date") or "9999-12-31",
            _PRIORITY_RANK.get(task.get("priority", ""), 9),
            task.get("created_at", ""),
        ))
        return [_public(task) for task in matches]
