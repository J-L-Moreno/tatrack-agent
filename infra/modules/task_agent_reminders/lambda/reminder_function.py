"""Daily reminder: if the student has overdue or soon-due tasks, ask the agent for a digest and email it via SNS."""
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config

OPEN_STATUSES = {"todo", "in_progress", "blocked"}
PROMPT = (
    "Genera el recordatorio diario de tareas siguiendo la skill reminder_digest. "
    "La fecha local de hoy es {today}. Responde solo con el texto del correo."
)

_dynamodb = boto3.resource("dynamodb")
_agentcore = boto3.client("bedrock-agentcore", config=Config(read_timeout=280, connect_timeout=10, retries={"max_attempts": 1}))
_sns = boto3.client("sns")


def _local_today(timezone_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError:
        print(f"Timezone {timezone_name} not available; using UTC")
        return datetime.now(timezone.utc).date()


def _due_tasks(table_name: str, actor_id: str, until: str) -> list[dict]:
    table = _dynamodb.Table(table_name)
    tasks: list[dict] = []
    kwargs = {"KeyConditionExpression": Key("actor_id").eq(actor_id)}
    while True:
        page = table.query(**kwargs)
        tasks.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return [task for task in tasks if task.get("status") in OPEN_STATUSES and task.get("due_date") and task["due_date"] <= until]


def _ask_agent(runtime_arn: str, actor_id: str, today: date) -> str:
    payload = {
        "prompt": PROMPT.format(today=today.isoformat()),
        "actor_id": actor_id,
        "session_id": f"reminder-{today.isoformat()}-{uuid.uuid4().hex}",
        "streaming": False,
        "source": "reminder",
    }
    response = _agentcore.invoke_agent_runtime(agentRuntimeArn=runtime_arn, payload=json.dumps(payload).encode("utf-8"))
    raw = response["response"].read().decode("utf-8")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return parsed if isinstance(parsed, str) else raw


def lambda_handler(event, context):
    actor_id = os.environ["REMINDER_ACTOR_ID"]
    today = _local_today(os.environ["REMINDER_TIMEZONE"])
    until = (today + timedelta(days=int(os.environ.get("LOOKAHEAD_DAYS", "1")))).isoformat()

    due = _due_tasks(os.environ["TASKS_TABLE_NAME"], actor_id, until)
    if not due:
        print(f"No overdue or upcoming tasks for {actor_id}; skipping reminder")
        return {"status": "skipped", "due_tasks": 0}

    message = _ask_agent(os.environ["AGENT_RUNTIME_ARN"], actor_id, today)
    _sns.publish(
        TopicArn=os.environ["SNS_TOPIC_ARN"],
        # SNS subjects must be ASCII and under 100 characters.
        Subject=f"Recordatorio de tareas - {today.isoformat()}",
        Message=message,
    )
    print(f"Reminder sent for {actor_id} with {len(due)} due tasks")
    return {"status": "sent", "due_tasks": len(due)}
