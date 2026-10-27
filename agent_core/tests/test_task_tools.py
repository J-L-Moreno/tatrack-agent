import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fakes import FakeTable
from tools import tasks
from tools.task_store import TaskStore

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)


class TaskToolsTestCase(unittest.TestCase):
    def setUp(self):
        self.table = FakeTable()
        self.store = TaskStore(self.table, timezone_name="America/Mexico_City", clock=lambda: NOW)
        self.actor_id = "ana"
        patchers = [
            patch.object(tasks, "get_task_store", return_value=self.store),
            patch.object(tasks, "get_config", side_effect=lambda: {"configurable": {"actor_id": self.actor_id}}),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, tool, **args):
        return json.loads(tool.invoke(args))


class CrudToolTests(TaskToolsTestCase):
    def test_create_get_update_flow_hides_actor_id(self):
        created = self.call(tasks.create_task, title="Estudiar", due_date="2026-10-27", tags=["mate"])["created"]
        self.assertNotIn("actor_id", created)

        fetched = self.call(tasks.get_task, task_id=created["task_id"])["task"]
        self.assertEqual(fetched["title"], "Estudiar")

        updated = self.call(tasks.update_task, task_id=created["task_id"], status="done")["updated"]
        self.assertEqual(updated["status"], "done")
        self.assertIn("completed_at", updated)

    def test_validation_errors_are_returned_to_the_model(self):
        result = self.call(tasks.create_task, title="Estudiar", due_date="next friday")
        self.assertIn("YYYY-MM-DD", result["error"])
        self.assertIn("not found", self.call(tasks.get_task, task_id="T-00000000")["error"])

    def test_missing_actor_id_is_rejected(self):
        self.actor_id = None
        self.assertIn("actor_id", self.call(tasks.create_task, title="Estudiar")["error"])
        self.assertEqual(self.table.items, {})

    def test_list_respects_limit_and_reports_total(self):
        for index in range(5):
            self.call(tasks.create_task, title=f"Tarea {index}", priority="high")

        result = self.call(tasks.list_tasks, priority="high", limit=2)
        self.assertEqual(result["total_matches"], 5)
        self.assertEqual(result["returned"], 2)
        self.assertEqual(len(result["tasks"]), 2)
        self.assertEqual(result["today"], "2026-10-25")
        self.assertIn("error", self.call(tasks.list_tasks, limit=0))


class DeleteToolTests(TaskToolsTestCase):
    def test_delete_requires_confirmation(self):
        task_id = self.call(tasks.create_task, title="Borrar")["created"]["task_id"]

        pending = self.call(tasks.delete_task, task_id=task_id)
        self.assertEqual(pending["status"], "confirmation_required")
        self.assertIsNotNone(self.store.get("ana", task_id))

        deleted = self.call(tasks.delete_task, task_id=task_id, confirmed=True)
        self.assertEqual(deleted["status"], "deleted")
        self.assertIsNone(self.store.get("ana", task_id))

    def test_cannot_delete_another_actors_task(self):
        task_id = self.call(tasks.create_task, title="Privada")["created"]["task_id"]
        self.actor_id = "luis"
        self.assertIn("not found", self.call(tasks.delete_task, task_id=task_id, confirmed=True)["error"])
        self.assertIsNotNone(self.store.get("ana", task_id))


class BulkAndSummaryToolTests(TaskToolsTestCase):
    def test_bulk_create_validates_all_tasks_first(self):
        result = self.call(tasks.create_tasks_bulk, tasks=[{"title": "Uno"}, {"title": " "}])
        self.assertIn("error", result)
        self.assertEqual(self.table.items, {})

        created = self.call(tasks.create_tasks_bulk, tasks=[{"title": "Uno"}, {"title": "Dos", "priority": "low"}])
        self.assertEqual([task["title"] for task in created["created"]], ["Uno", "Dos"])

    def test_bulk_create_limit(self):
        result = self.call(tasks.create_tasks_bulk, tasks=[{"title": f"T{i}"} for i in range(16)])
        self.assertIn("between 1 and 15", result["error"])

    def test_summarize_progress(self):
        self.call(tasks.create_task, title="Vencida", due_date="2026-10-01")
        self.call(tasks.create_task, title="Hecha", status="done")
        summary = self.call(tasks.summarize_progress)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["completion_rate_pct"], 50.0)
        self.assertEqual(len(summary["overdue"]), 1)


if __name__ == "__main__":
    unittest.main()
