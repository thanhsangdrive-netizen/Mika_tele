import hashlib
import hmac
import json
import secrets
import threading
import time

from .api import ApiError

TERMINAL = {"done", "failed", "cancelled"}
KNOWN = TERMINAL | {"starting", "running", "paused", "waiting_for_answer", "waiting_on_phone"}
HELP = """Mika Telegram Assistant (Private chat only)

Send any message to start a task or answer a question from Mika.

Commands:
/status - Show current task progress and details
/answer <text> - Answer a question requested by Mika
/steer <text> - Send additional instructions to a running task
/cancel - Cancel current task
/new - Reset conversation and start a new one
/reset checked - Clear local tracking if an error occurred
/help - Show this help menu

Note: For payments, login credentials, and verification codes (OTP), Mika will pause and request you to operate directly on the phone."""


def normalize(data):
    """Normalize Telegram update to standard event format.
    Accept private text messages and callback queries."""
    if "message" in data:
        msg = data["message"]
        chat = msg.get("chat", {})
        sender = msg.get("from", {})
        if chat.get("type") != "private" or sender.get("is_bot"):
            return None
        text = (msg.get("text") or "").strip()
        if not text or len(text) > 4000:
            return None
        return {
            "id": str(msg["message_id"]),
            "user": str(sender["id"]),
            "chat": str(chat["id"]),
            "text": text,
            "created_at": msg.get("date", int(time.time())),
            "reply_to": str(msg.get("reply_to_message", {}).get("message_id")) if "reply_to_message" in msg else None,
        }
    elif "callback_query" in data:
        cb = data["callback_query"]
        sender = cb.get("from", {})
        msg = cb.get("message", {})
        chat = msg.get("chat", {})
        data_text = (cb.get("data") or "").strip()
        return {
            "id": f"cb_{cb['id']}",
            "user": str(sender["id"]),
            "chat": str(chat["id"]),
            "text": data_text,
            "created_at": int(time.time()),
            "reply_to": str(msg.get("message_id")) if "message_id" in msg else None,
            "callback_query_id": cb["id"],
        }
    return None


def describe(task):
    status = task.get("status", "unknown")
    title = {
        "done": "✅ Task completed",
        "failed": "❌ Task failed",
        "cancelled": "🛑 Task cancelled",
        "waiting_for_answer": "❓ Mika needs your answer",
        "waiting_on_phone": "📱 Please handle this step directly on your phone",
        "paused": "⏸️ Task paused",
        "running": "⚡ Running...",
        "starting": "⏳ Starting..."
    }.get(status, "Unknown task status")

    detail = (task.get("answer") or task.get("question") or task.get("message") or
              task.get("progress") or task.get("reason") or "")
    result = f"{title}\nTask ID: `{task.get('task_id', '?')}`"
    if detail:
        result += f"\n\n{detail}"
    if task.get("options"):
        result += "\n\nOptions: " + " / ".join(f"`{x}`" for x in task["options"])
    if status == "waiting_for_answer":
        result += "\n\n👉 Reply directly to this message or send `/answer <text>`."
    elif status == "waiting_on_phone":
        result += "\n\n⚠️ This step involves security/payment and must be completed on the phone."
    elif status == "done":
        if task.get("verified") is True:
            result += "\n\n✨ Result verified."
        if task.get("unconfirmed"):
            result += f"\n\nUnconfirmed: {json.dumps(task['unconfirmed'], ensure_ascii=False)}"
    return result


class Bridge:
    def __init__(self, api, store, send, allowed_users=()):
        self.api, self.store, self.send = api, store, send
        self.allowed = set(str(u) for u in allowed_users)
        self.pair_code, self.pair_deadline = None, 0
        self.session_lock = threading.Lock()

    def owners(self):
        return self.allowed | {r["id"] for r in self.store.execute("SELECT id FROM owners")}

    def enable_pairing(self):
        if self.owners():
            return None
        self.pair_code = secrets.token_urlsafe(12)
        self.pair_deadline = time.monotonic() + 600
        return self.pair_code

    def receive(self, data):
        event = normalize(data)
        if not event:
            return False
        pairing = (self.pair_code and time.monotonic() < self.pair_deadline and
                   event["text"].startswith("/pair ") and
                   hmac.compare_digest(event["text"][6:].strip(), self.pair_code))
        if pairing:
            with self.store.lock:
                if not self.owners():
                    self.store.execute("INSERT INTO owners VALUES(?)", (event["user"],))
                    self.pair_code = None
            event["text"] = "/help"

        if event["user"] not in self.owners():
            if not self.owners():
                self.send(event["chat"], "Bot is not paired yet. Please check server console for pairing code.", None)
            return False
        return self.store.enqueue(event)

    def reply(self, event, text, suffix="reply"):
        key = hashlib.sha256((event["id"] + suffix).encode()).hexdigest()
        return self.send(event["chat"], text, key)

    def can_answer(self, peer, task, event):
        if not task or task["status"] != "waiting_for_answer":
            return False
        notice = hashlib.sha256(describe(task).encode()).hexdigest()
        question = self.store.question(peer, task["task_id"], notice)
        if question is None:
            return False
        message_ids, shown_at_ms = question
        parent = event.get("reply_to")
        if parent and parent in message_ids:
            return True
        return shown_at_ms is not None and event["created_at"] > shown_at_ms / 1000

    def recover(self):
        for row in self.store.execute("SELECT * FROM inbox WHERE state='processing'"):
            event = json.loads(row["payload"])
            if event["user"] in self.owners():
                self.store.update(event["chat"] + ":" + event["user"], uncertain=1)
                self.reply(event, "The connector was restarted while processing a message. Execution is uncertain; it was not replayed. "
                           "Check your phone, then send /reset checked.", "recovery")
            self.store.execute("UPDATE inbox SET state='done' WHERE id=?", (row["id"],))

    def work_once(self):
        event = self.store.pop()
        if not event:
            return False
        try:
            if event["user"] not in self.owners():
                return True
            if time.time() - event.get("created_at", 0) > 300:
                self.reply(event, "This queued message expired; no phone action was submitted.", "expired")
            else:
                with self.session_lock:
                    self.handle(event)
        except ApiError as exc:
            if exc.uncertain:
                self.store.update(event["chat"] + ":" + event["user"], uncertain=1)
                text = "The phone may have accepted the request. It was not retried. Check the phone before proceeding."
            else:
                text = f"Mika request failed ({exc.code}). Check phone connection and task status."
            self.reply(event, text, "error")
        except Exception:
            self.store.update(event["chat"] + ":" + event["user"], uncertain=1)
            raise
        finally:
            self.store.execute("UPDATE inbox SET state='done' WHERE id=?", (event["id"],))
        return True

    def handle(self, e):
        peer, text = e["chat"] + ":" + e["user"], e["text"]
        session = self.store.session(peer)
        command, _, arg = text.partition(" ")
        if command in {"/start", "/help"}:
            return self.reply(e, HELP)
        if command == "/reset":
            if arg != "checked":
                return self.reply(e, "This clears local tracking. Check the phone first, then send `/reset checked`.")
            self.store.update(peer, task_id=None, conversation=None, uncertain=0, notice="")
            return self.reply(e, "Local tracking cleared. Phone tasks were not cancelled.")
        if command == "/status":
            if not session["task_id"]:
                return self.reply(e, "No active or recent task. " + ("Last write was uncertain; check the phone." if session["uncertain"] else ""))
            task = self.api.task(session["task_id"])
            text_desc = describe(task)
            sent = self.reply(e, text_desc)
            if task["status"] == "waiting_for_answer":
                self.store.remember_question(peer, task["task_id"], hashlib.sha256(text_desc.encode()).hexdigest(), sent)
            return

        if session["uncertain"]:
            return self.reply(e, "An operation was interrupted and is uncertain. Check your phone, then send `/reset checked`.")

        task = self.api.task(session["task_id"]) if session["task_id"] else None
        if task and task.get("status") not in KNOWN:
            raise ApiError("unknown_task_status")
        active = task and task["status"] not in TERMINAL

        if command == "/new":
            if active:
                return self.reply(e, "A task is still active. Please wait or use /cancel first.")
            self.store.update(peer, conversation=None, task_id=None, notice="")
            return self.reply(e, "Session cleared. Your next message will start a new conversation.")

        if command in {"/answer", "/steer", "/cancel"}:
            if not active:
                return self.reply(e, "There is no active task.")
            action = command[1:]
            if action == "answer" and task["status"] != "waiting_for_answer":
                return self.reply(e, "No pending question. For confirmations and logins, use the phone.")
            if action == "answer" and not self.can_answer(peer, task, e):
                return self.reply(e, "Answer does not match current question. Send /status to inspect.")
            if action == "steer" and task["status"] != "running":
                return self.reply(e, "Only a running task accepts /steer.")
            result = self.api.action(task["task_id"], action, None if action == "cancel" else arg)
            if not result.get("accepted"):
                return self.reply(e, "Action was not accepted. Check /status.")
            return self.reply(e, f"Action `{action}` submitted. Check /status for progress.")

        if command.startswith("/"):
            return self.reply(e, "Unknown command. Send /help for available commands.")

        if active:
            if task["status"] == "waiting_for_answer":
                self.api.action(task["task_id"], "answer", text)
                return self.reply(e, "Answer submitted to Mika.")
            return self.reply(e, "A task is already running! Use `/steer <instruction>` or `/status`.")

        self.store.update(peer, uncertain=1)
        try:
            result = self.api.start(text, session["conversation"])
        except ApiError as exc:
            if not exc.uncertain:
                self.store.update(peer, uncertain=0)
            raise
        if not result.get("task_id") or not result.get("conversation") or result.get("status") not in KNOWN:
            raise ApiError("incompatible_task_response", uncertain=True)

        self.api.safe_id(result["task_id"])
        self.store.update(peer, task_id=result["task_id"], conversation=result["conversation"], uncertain=0, notice="")
        self.reply(e, f"🚀 Task submitted to phone!\nTask ID: `{result['task_id']}`\n\nUse /status to monitor progress.")

    def poll_once(self):
        for row in self.store.execute("SELECT * FROM sessions WHERE task_id IS NOT NULL"):
            s = dict(row)
            if s["notice"].startswith("terminal:"):
                continue
            chat, user = s["peer"].split(":", 1)
            if user not in self.owners():
                continue
            try:
                task = self.api.task(s["task_id"])
                status = task.get("status")
                if status not in KNOWN:
                    raise ApiError("unknown_task_status")
                if status in {"starting", "running"}:
                    continue
                with self.session_lock:
                    current = self.store.session(s["peer"])
                    if current["task_id"] != s["task_id"]:
                        continue
                    text_desc = describe(task)
                    notice = hashlib.sha256(text_desc.encode()).hexdigest()
                    saved_notice = "terminal:" + notice if status in TERMINAL else notice
                    if saved_notice == current["notice"] and (status != "waiting_for_answer" or
                            self.store.question(s["peer"], s["task_id"], notice) is not None):
                        continue
                    sent = self.send(chat, text_desc, hashlib.sha256((s["task_id"] + notice).encode()).hexdigest())
                    if status == "waiting_for_answer":
                        self.store.remember_question(s["peer"], s["task_id"], notice, sent)
                    self.store.execute("UPDATE sessions SET notice=? WHERE peer=? AND task_id=?",
                                       (saved_notice, s["peer"], s["task_id"]))
            except ApiError as exc:
                if exc.status == 404 or exc.code.startswith("incompatible") or exc.code == "unknown_task_status":
                    current = self.store.session(s["peer"])
                    if current["task_id"] != s["task_id"]:
                        continue
                    notice = "error:" + exc.code
                    if notice != current["notice"]:
                        self.send(chat, f"Cannot track task ({exc.code}). The phone may have restarted or finished.",
                                  hashlib.sha256((s["task_id"] + notice).encode()).hexdigest())
                    self.store.execute("UPDATE sessions SET uncertain=1, notice=? WHERE peer=? AND task_id=?",
                                       (notice, s["peer"], s["task_id"]))
