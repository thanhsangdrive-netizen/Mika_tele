import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from mika_telegram.api import ApiError, MikaApi
from mika_telegram.bridge import Bridge, normalize, describe
from mika_telegram.store import Store


def tg_message(mid=101, text="Test task", user=12345, chat_type="private"):
    return {
        "message": {
            "message_id": mid,
            "chat": {"id": user, "type": chat_type},
            "from": {"id": user, "is_bot": False},
            "text": text,
            "date": int(time.time()),
        }
    }


class FakeApi:
    def __init__(self):
        self.writes = []
        self.status = {"task_id": "task_1", "conversation": "tele-test", "status": "running"}
        self.error = None

    def task(self, tid):
        return dict(self.status)

    def start(self, goal, conversation=None):
        self.writes.append(("start", goal, conversation))
        if self.error:
            raise self.error
        return dict(self.status)

    def action(self, tid, action, text=None):
        self.writes.append((action, text))
        return {"accepted": True}

    safe_id = staticmethod(MikaApi.safe_id)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.db")
        self.api, self.sent = FakeApi(), []
        self.bridge = Bridge(self.api, self.store, self.send, ["12345"])

    def send(self, *args):
        self.sent.append(args)
        return {"bot_" + str(len(self.sent)): int(time.time() * 1000) - 1}

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_normalize(self):
        event = normalize(tg_message(101, "Hello Mika", 12345))
        self.assertIsNotNone(event)
        self.assertEqual(event["id"], "101")
        self.assertEqual(event["user"], "12345")
        self.assertEqual(event["text"], "Hello Mika")

    def test_normalize_ignores_group_or_bot(self):
        # Ignore group
        msg_group = tg_message(102, "Hello", 12345, chat_type="group")
        self.assertIsNone(normalize(msg_group))

        # Ignore bot
        msg_bot = tg_message(103, "Hello", 12345)
        msg_bot["message"]["from"]["is_bot"] = True
        self.assertIsNone(normalize(msg_bot))

    def test_pairing_workflow(self):
        # Empty owners
        store2 = Store(Path(self.tmp.name) / "state2.db")
        bridge2 = Bridge(self.api, store2, self.send, [])
        pair_code = bridge2.enable_pairing()
        self.assertIsNotNone(pair_code)

        # Unauthorized user without pairing code
        self.assertFalse(bridge2.receive(tg_message(201, "Run something", 99999)))

        # Pair with code
        self.assertTrue(bridge2.receive(tg_message(202, f"/pair {pair_code}", 99999)))
        self.assertIn("99999", bridge2.owners())
        store2.db.close()

    def test_submit_task(self):
        self.assertTrue(self.bridge.receive(tg_message(101, "Check weather", 12345)))
        self.assertTrue(self.bridge.work_once())
        self.assertEqual(len(self.api.writes), 1)
        self.assertEqual(self.api.writes[0][0], "start")
        self.assertEqual(self.api.writes[0][1], "Check weather")

    def test_status_command(self):
        # First start a task
        self.bridge.receive(tg_message(101, "Check weather", 12345))
        self.bridge.work_once()

        # Send /status
        self.bridge.receive(tg_message(102, "/status", 12345))
        self.bridge.work_once()
        self.assertTrue(any("Task ID" in str(s) for s in self.sent))


if __name__ == "__main__":
    unittest.main()
