import unittest
from datetime import datetime, timedelta, timezone

from fakes import FakeTable, MutableClock
from tools.task_store import TaskNotFoundError, TaskStore, TaskValidationError

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)  # 09:00 in America/Mexico_City


class TaskStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.table = FakeTable(page_size=2)
        self.clock = MutableClock(NOW)
        self.store = TaskStore(self.table, timezone_name="America/Mexico_City", clock=self.clock)


class CreateTests(TaskStoreTestCase):
    def test_create_applies_defaults_and_normalizes_fields(self):
        task = self.store.create("ana", "  Leer capítulo 3  ", tags=["Cálculo II", "cálculo ii", " "])

        self.assertRegex(task["task_id"], r"^T-[0-9a-f]{8}$")
        self.assertEqual(task["title"], "Leer capítulo 3")
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["priority"], "medium")
        self.assertEqual(task["tags"], ["cálculo-ii"])
        self.assertEqual(task["created_at"], "2026-10-25T15:00:00Z")
        self.assertNotIn("due_date", task)
        self.assertNotIn("completed_at", task)

    def test_create_done_task_records_completion(self):
        task = self.store.create("ana", "Entregar tarea", status="done")
        self.assertEqual(task["completed_at"], "2026-10-25T15:00:00Z")

    def test_create_rejects_invalid_fields(self):
        invalid_inputs = [
            {"title": "   "},
            {"title": "x" * 201},
            {"title": "ok", "priority": "critical"},
            {"title": "ok", "status": "archived"},
            {"title": "ok", "due_date": "25/10/2026"},
            {"title": "ok", "tags": [f"tag{i}" for i in range(11)]},
            {"title": "ok", "description": "d" * 2001},
        ]
        for fields in invalid_inputs:
            with self.subTest(fields=fields), self.assertRaises(TaskValidationError):
                self.store.create("ana", **fields)
        self.assertEqual(self.table.items, {})

    def test_create_many_is_all_or_nothing(self):
        with self.assertRaises(TaskValidationError):
            self.store.create_many("ana", [{"title": "Uno"}, {"title": "Dos", "due_date": "mañana"}])
        self.assertEqual(self.table.items, {})

        created = self.store.create_many("ana", [{"title": "Uno"}, {"title": "Dos", "due_date": "2026-10-30"}])
        self.assertEqual(len(created), 2)
        self.assertEqual(len({task["task_id"] for task in created}), 2)


class ActorIsolationTests(TaskStoreTestCase):
    def test_other_actor_cannot_read_update_or_delete(self):
        task = self.store.create("ana", "Privada")

        self.assertIsNone(self.store.get("luis", task["task_id"]))
        self.assertEqual(self.store.find("luis"), [])
        with self.assertRaises(TaskNotFoundError):
            self.store.update("luis", task["task_id"], status="done")
        with self.assertRaises(TaskNotFoundError):
            self.store.delete("luis", task["task_id"])
        self.assertEqual(self.store.get("ana", task["task_id"])["status"], "todo")


class UpdateTests(TaskStoreTestCase):
    def test_partial_update_and_completion_timestamps(self):
        task = self.store.create("ana", "Ensayo", description="Borrador", due_date="2026-10-30")

        self.clock.now = NOW + timedelta(hours=1)
        done = self.store.update("ana", task["task_id"], status="done", description="")
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["completed_at"], "2026-10-25T16:00:00Z")
        self.assertNotIn("description", done)
        self.assertEqual(done["due_date"], "2026-10-30")
        self.assertEqual(done["updated_at"], "2026-10-25T16:00:00Z")

        reopened = self.store.update("ana", task["task_id"], status="in_progress")
        self.assertNotIn("completed_at", reopened)

    def test_update_requires_fields_and_existing_task(self):
        task = self.store.create("ana", "Ensayo")
        with self.assertRaises(TaskValidationError):
            self.store.update("ana", task["task_id"])
        with self.assertRaises(TaskNotFoundError):
            self.store.update("ana", "T-00000000", title="Nuevo")

    def test_clear_due_date_and_tags(self):
        task = self.store.create("ana", "Ensayo", due_date="2026-10-30", tags=["ingles"])
        updated = self.store.update("ana", task["task_id"], due_date="", tags=[])
        self.assertNotIn("due_date", updated)
        self.assertEqual(updated["tags"], [])


class DeleteTests(TaskStoreTestCase):
    def test_delete_returns_old_task(self):
        task = self.store.create("ana", "Borrar")
        deleted = self.store.delete("ana", task["task_id"])
        self.assertEqual(deleted["title"], "Borrar")
        self.assertIsNone(self.store.get("ana", task["task_id"]))
        with self.assertRaises(TaskNotFoundError):
            self.store.delete("ana", task["task_id"])


class FindTests(TaskStoreTestCase):
    def setUp(self):
        super().setUp()
        self.overdue = self.store.create("ana", "Vencida", due_date="2026-10-20", priority="high", tags=["fisica"])
        self.today = self.store.create("ana", "Para hoy", due_date="2026-10-25", priority="urgent")
        self.later = self.store.create("ana", "Para luego", due_date="2026-11-10", description="Laboratorio")
        self.no_date = self.store.create("ana", "Sin fecha", priority="low", tags=["fisica"])
        self.done = self.store.create("ana", "Hecha", due_date="2026-10-01", status="done")

    def ids(self, tasks):
        return [task["task_id"] for task in tasks]

    def test_paginates_and_sorts_by_due_date_then_priority(self):
        self.assertEqual(
            self.ids(self.store.find("ana")),
            self.ids([self.done, self.overdue, self.today, self.later, self.no_date]),
        )

    def test_filters(self):
        cases = {
            "status": ({"statuses": ["done"]}, [self.done]),
            "priority": ({"priority": "urgent"}, [self.today]),
            "tag": ({"tag": "Fisica"}, [self.overdue, self.no_date]),
            "due range inclusive": ({"due_after": "2026-10-20", "due_before": "2026-10-25"}, [self.overdue, self.today]),
            "overdue": ({"overdue_only": True}, [self.overdue]),
            "text in description": ({"text": "laboratorio"}, [self.later]),
            "completed_after": ({"completed_after": "2026-10-25"}, [self.done]),
        }
        for name, (filters, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.ids(self.store.find("ana", **filters)), self.ids(expected))

    def test_today_uses_user_timezone(self):
        self.clock.now = datetime(2026, 10, 26, 3, 0, tzinfo=timezone.utc)  # still Oct 25 in Mexico City
        self.assertEqual(self.store.today().isoformat(), "2026-10-25")
        self.assertEqual(self.ids(self.store.find("ana", overdue_only=True)), self.ids([self.overdue]))

    def test_rejects_invalid_filters(self):
        with self.assertRaises(TaskValidationError):
            self.store.find("ana", due_before="ayer")


class SummarizeTests(TaskStoreTestCase):
    def test_summary_counts(self):
        self.store.create("ana", "Vencida", due_date="2026-10-20", priority="high")
        self.store.create("ana", "Pronto", due_date="2026-10-28")
        self.store.create("ana", "Lejos", due_date="2026-12-01", status="blocked")
        self.store.create("ana", "Hecha", status="done")

        summary = self.store.summarize("ana")

        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["by_status"], {"todo": 2, "in_progress": 0, "blocked": 1, "done": 1})
        self.assertEqual(summary["open_by_priority"], {"low": 0, "medium": 2, "high": 1, "urgent": 0})
        self.assertEqual(summary["completion_rate_pct"], 25.0)
        self.assertEqual(summary["completed_last_7_days"], 1)
        self.assertEqual([task["title"] for task in summary["overdue"]], ["Vencida"])
        self.assertEqual([task["title"] for task in summary["due_soon"]], ["Pronto"])

    def test_empty_summary_and_invalid_window(self):
        self.assertEqual(self.store.summarize("ana")["completion_rate_pct"], 0.0)
        with self.assertRaises(TaskValidationError):
            self.store.summarize("ana", upcoming_days=0)


if __name__ == "__main__":
    unittest.main()
