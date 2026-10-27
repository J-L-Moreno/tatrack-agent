"""In-memory stand-ins for AWS resources used by the unit tests."""
import copy

from botocore.exceptions import ClientError


def conditional_failure(operation: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
        operation,
    )


class FakeTable:
    """Implements the subset of the boto3 Table API used by TaskStore (paginates queries)."""

    def __init__(self, page_size: int = 2):
        self.items: dict[tuple[str, str], dict] = {}
        self.page_size = page_size

    def put_item(self, Item, ConditionExpression=None):
        key = (Item["actor_id"], Item["task_id"])
        exists = key in self.items
        if ConditionExpression == "attribute_not_exists(task_id)" and exists:
            raise conditional_failure("PutItem")
        if ConditionExpression == "attribute_exists(task_id)" and not exists:
            raise conditional_failure("PutItem")
        self.items[key] = copy.deepcopy(Item)
        return {}

    def get_item(self, Key):
        item = self.items.get((Key["actor_id"], Key["task_id"]))
        return {"Item": copy.deepcopy(item)} if item else {}

    def delete_item(self, Key, ConditionExpression=None, ReturnValues=None):
        key = (Key["actor_id"], Key["task_id"])
        if key not in self.items:
            raise conditional_failure("DeleteItem")
        return {"Attributes": self.items.pop(key)}

    def query(self, KeyConditionExpression, ExclusiveStartKey=None):
        actor_id = KeyConditionExpression.get_expression()["values"][1]
        matching = sorted(
            (item for (owner, _), item in self.items.items() if owner == actor_id),
            key=lambda item: item["task_id"],
        )
        start = 0
        if ExclusiveStartKey:
            start = 1 + next(
                index for index, item in enumerate(matching) if item["task_id"] == ExclusiveStartKey["task_id"]
            )
        page = matching[start:start + self.page_size]
        response = {"Items": copy.deepcopy(page)}
        if start + self.page_size < len(matching):
            response["LastEvaluatedKey"] = {"actor_id": actor_id, "task_id": page[-1]["task_id"]}
        return response


class MutableClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now
