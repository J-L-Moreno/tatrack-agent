import io
import json
import os
import unittest

os.environ.setdefault("RATE_LIMIT", "1000/minute")

from fastapi.testclient import TestClient

import main
from app_logging import get_logger
from auth import APIKeyProvider
from dependencies import get_api_key_provider, get_message_service, get_task_repository
from repositories import ResponseRepository, TaskRepository
from services import AgentRuntimeService, MessageService

API_KEY = "test-key"
HEADERS = {"x-api-key": API_KEY}


class FakeSecrets:
    def get_secret_value(self, *, SecretId):
        return {"SecretString": f"{API_KEY},other-key"}


class FakeTable:
    def __init__(self, items):
        self.items = items
        self.puts = []

    def get_item(self, *, Key):
        for item in self.items:
            if all(item.get(name) == value for name, value in Key.items()):
                return {"Item": dict(item)}
        return {}

    def query(self, **kwargs):
        actor_id = kwargs["KeyConditionExpression"].get_expression()["values"][1]
        return {"Items": [dict(item) for item in self.items if item["actor_id"] == actor_id]}

    def put_item(self, *, Item):
        self.puts.append(Item)


class FakeResource:
    def __init__(self, table):
        self.table = table

    def Table(self, name):
        return self.table


class FakeAgentCoreClient:
    def __init__(self):
        self.payloads = []

    def invoke_agent_runtime(self, *, agentRuntimeArn, payload):
        self.payloads.append(json.loads(payload))
        return {"contentType": "application/json", "response": io.BytesIO(json.dumps("Listo ✅").encode())}


TASKS = [
    {"actor_id": "ana", "task_id": "T-0000000a", "title": "Luego", "status": "todo", "priority": "low",
     "due_date": "2026-11-10", "tags": ["fisica"]},
    {"actor_id": "ana", "task_id": "T-0000000b", "title": "Pronto", "status": "done", "priority": "high",
     "due_date": "2026-10-26", "tags": []},
    {"actor_id": "luis", "task_id": "T-0000000c", "title": "Ajena", "status": "todo", "priority": "low", "tags": []},
]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.agentcore = FakeAgentCoreClient()
        self.responses = FakeTable([])
        runtime = AgentRuntimeService(self.agentcore, "arn:runtime", 25, 5)

        main.app.dependency_overrides = {
            get_api_key_provider: lambda: APIKeyProvider(FakeSecrets(), "secret", 300, get_logger()),
            get_task_repository: lambda: TaskRepository(FakeResource(FakeTable(TASKS)), "tasks"),
            get_message_service: lambda: MessageService(
                ResponseRepository(FakeResource(self.responses), "responses", 60), runtime, get_logger()
            ),
        }
        self.client = TestClient(main.app)
        self.addCleanup(main.app.dependency_overrides.clear)

    def test_health_is_public(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_requires_valid_api_key(self):
        self.assertEqual(self.client.get("/tasks", params={"actor_id": "ana"}).status_code, 422)
        self.assertEqual(
            self.client.get("/tasks", params={"actor_id": "ana"}, headers={"x-api-key": "bad"}).status_code, 403
        )

    def test_list_tasks_is_scoped_filtered_and_sorted(self):
        body = self.client.get("/tasks", params={"actor_id": "ana"}, headers=HEADERS).json()
        self.assertEqual([task["task_id"] for task in body["tasks"]], ["T-0000000b", "T-0000000a"])
        self.assertTrue(all("actor_id" not in task for task in body["tasks"]))

        filtered = self.client.get("/tasks", params={"actor_id": "ana", "tag": "FISICA"}, headers=HEADERS).json()
        self.assertEqual(filtered["count"], 1)

    def test_query_validation(self):
        bad_requests = [
            ("/tasks", {"actor_id": "ana@uni.mx"}),
            ("/tasks", {"actor_id": "ana", "status": "archived"}),
            ("/tasks/not-an-id", {"actor_id": "ana"}),
        ]
        for path, params in bad_requests:
            with self.subTest(path=path, params=params):
                self.assertEqual(self.client.get(path, params=params, headers=HEADERS).status_code, 422)

    def test_get_task_is_scoped_to_actor(self):
        self.assertEqual(
            self.client.get("/tasks/T-0000000a", params={"actor_id": "ana"}, headers=HEADERS).json()["title"], "Luego"
        )
        self.assertEqual(
            self.client.get("/tasks/T-0000000c", params={"actor_id": "ana"}, headers=HEADERS).status_code, 404
        )

    def test_sync_message_decodes_runtime_json_and_tracks_response(self):
        response = self.client.post(
            "/messages",
            headers=HEADERS,
            json={"prompt": "Crea una tarea", "session_id": "session-1", "actor_id": "ana"},
        )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "COMPLETED")
        self.assertEqual(body["response"], "Listo ✅")
        self.assertEqual(self.responses.puts[0]["id"], body["response_id"])
        self.assertEqual(self.agentcore.payloads[0]["source"], "chat")

    def test_message_validation(self):
        invalid = [
            {"prompt": "", "session_id": "s1", "actor_id": "ana"},
            {"prompt": "hola", "session_id": "s1", "actor_id": "ana.lopez"},
            {"prompt": "x" * 4001, "session_id": "s1", "actor_id": "ana"},
        ]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/messages", headers=HEADERS, json=body).status_code, 422)


if __name__ == "__main__":
    unittest.main()
