import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage

import main


class FakeAgent:
    def __init__(self, events):
        self.events = events

    def astream(self, *args, **kwargs):
        async def generate():
            for delay, event in self.events:
                await asyncio.sleep(delay)
                yield event

        return generate()


class StalledAgent:
    def astream(self, *args, **kwargs):
        async def generate():
            await asyncio.Event().wait()
            yield

        return generate()


class BuildInvokeConfigTests(unittest.TestCase):
    def test_chat_requests_write_memory(self):
        cfg = main.build_invoke_config({"session_id": "s1", "actor_id": "ana"})
        self.assertEqual(cfg["configurable"], {"thread_id": "s1", "actor_id": "ana", "memory_write": True})
        self.assertEqual(cfg["recursion_limit"], main.config.recursion_limit)

    def test_reminder_requests_do_not_write_memory(self):
        cfg = main.build_invoke_config({"actor_id": "ana", "source": "reminder"})
        self.assertFalse(cfg["configurable"]["memory_write"])
        self.assertTrue(cfg["configurable"]["thread_id"])


class InvokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_prompt_and_actor(self):
        self.assertEqual(await main.invoke({"prompt": "hola"}), main.MISSING_FIELDS_MESSAGE)
        self.assertEqual(await main.invoke({"actor_id": "ana"}), main.MISSING_FIELDS_MESSAGE)

    async def test_sync_response_strips_think_tags(self):
        final = AIMessage("<think>razonando</think>\nListo, creé la tarea.")
        events = [(0, {"type": "values", "data": {"messages": [final]}})]
        with patch.object(main, "agent", FakeAgent(events)):
            response = await main.invoke({"prompt": "Crea una tarea", "actor_id": "ana"})
        self.assertEqual(response, "Listo, creé la tarea.")

    async def test_inactivity_timeout(self):
        with (
            patch.object(main, "agent", StalledAgent()),
            patch.object(main, "config", SimpleNamespace(agent_inactivity_timeout_sec=0.01)),
        ):
            with self.assertRaises(main.AgentInactivityTimeoutError):
                await main._invoke_with_inactivity_timeout("prompt", {})


if __name__ == "__main__":
    unittest.main()
