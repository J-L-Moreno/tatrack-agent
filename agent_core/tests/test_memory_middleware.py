import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph_checkpoint_aws import AgentCoreMemoryStore

from middlewares import memory
from middlewares.memory import MemoryMiddleware


class FakeStore:
    def __init__(self, records=None, fail=False):
        self.records = records or {}
        self.fail = fail
        self.puts = []
        self.searches = []

    def put(self, namespace, key, value):
        if self.fail:
            raise RuntimeError("put failed")
        self.puts.append((namespace, value))

    def search(self, namespace, *, query, limit):
        if self.fail:
            raise RuntimeError("search failed")
        self.searches.append((namespace, query, limit))
        return [SimpleNamespace(value={"content": text}) for text in self.records.get(namespace, [])]


class FakeRequest:
    def __init__(self, state, system_message):
        self.state = state
        self.system_message = system_message

    def override(self, **overrides):
        return FakeRequest(self.state, overrides.get("system_message", self.system_message))


class MemoryMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.middleware = MemoryMiddleware(namespace_prefix="tasks", search_limit=3)
        self.configurable = {"actor_id": "ana", "thread_id": "session-1", "memory_write": True}
        patcher = patch.object(memory, "get_config", side_effect=lambda: {"configurable": self.configurable})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_before_agent(self, store, messages=None):
        state = {"messages": messages or [HumanMessage("Prefiero prioridad alta"), AIMessage("Entendido")]}
        return self.middleware.before_agent(state, SimpleNamespace(store=store))

    def test_stores_latest_user_message_and_searches_both_strategies(self):
        store = FakeStore({
            ("tasks", "user", "ana", "preferences", ""): ["Prefiere prioridad alta por defecto"],
            ("tasks", "user", "ana", "semantic", ""): ["Cursa Cálculo II"],
        })

        result = self.run_before_agent(store)

        self.assertEqual(len(store.puts), 1)
        namespace, value = store.puts[0]
        self.assertEqual(namespace, ("ana", "session-1"))
        self.assertEqual(value["message"].content, "Prefiero prioridad alta")
        self.assertEqual(
            [search[0] for search in store.searches],
            [("tasks", "user", "ana", "preferences", ""), ("tasks", "user", "ana", "semantic", "")],
        )
        self.assertTrue(all(search[1:] == ("Prefiero prioridad alta", 3) for search in store.searches))
        self.assertIn("### Preferencias del usuario\n- Prefiere prioridad alta por defecto", result["long_term_memories"])
        self.assertIn("### Contexto de conversaciones anteriores\n- Cursa Cálculo II", result["long_term_memories"])

    def test_reminder_runs_read_but_do_not_write(self):
        self.configurable["memory_write"] = False
        store = FakeStore({("tasks", "user", "ana", "preferences", ""): ["Tono breve"]})

        result = self.run_before_agent(store)

        self.assertEqual(store.puts, [])
        self.assertIn("Tono breve", result["long_term_memories"])

    def test_store_errors_do_not_break_the_turn(self):
        self.assertEqual(self.run_before_agent(FakeStore(fail=True)), {"long_term_memories": ""})

    def test_noop_without_store_or_actor(self):
        self.assertEqual(self.run_before_agent(None), {"long_term_memories": ""})
        self.configurable["actor_id"] = None
        store = FakeStore()
        self.assertEqual(self.run_before_agent(store), {"long_term_memories": ""})
        self.assertEqual(store.puts, [])

    def test_injects_memories_into_system_prompt_only_when_present(self):
        system = SystemMessage("Prompt base")

        unchanged = FakeRequest({"long_term_memories": ""}, system)
        self.assertIs(self.middleware._inject_memories(unchanged), unchanged)

        injected = self.middleware._inject_memories(FakeRequest({"long_term_memories": "### Preferencias\n- X"}, system))
        text = "".join(block["text"] for block in injected.system_message.content_blocks)
        self.assertTrue(text.startswith("Prompt base"))
        self.assertIn("## Memoria a largo plazo del usuario", text)
        self.assertIn("- X", text)

    def test_search_namespace_matches_terraform_strategy_template(self):
        store = AgentCoreMemoryStore.__new__(AgentCoreMemoryStore)  # skip boto3 client creation
        rendered = store._convert_namespace_to_string(("tasks", "user", "ana", "preferences", ""))
        self.assertEqual(rendered, "/tasks/user/{actorId}/preferences/".replace("{actorId}", "ana"))


if __name__ == "__main__":
    unittest.main()
