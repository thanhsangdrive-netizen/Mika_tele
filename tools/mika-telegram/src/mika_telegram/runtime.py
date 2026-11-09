"""Pure standard library Telegram Bot API transport. No external dependencies required."""
import json
import logging
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request


class TelegramSender:
    def __init__(self, bot_token):
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.lock = threading.Lock()
        self.ssl_context = ssl.create_default_context()

    def __call__(self, chat_id, text, key=None):
        """Send message, chunking if text exceeds 4000 characters."""
        chunks, current = [], ""
        for char in text:
            if len((current + char).encode("utf-8")) > 3900:
                chunks.append(current)
                current = ""
            current += char
        chunks.append(current)

        sent = {}
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with self.lock:
                try:
                    with urllib.request.urlopen(req, timeout=15, context=self.ssl_context) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        if res.get("ok"):
                            msg = res.get("result", {})
                            msg_id = str(msg.get("message_id"))
                            sent[msg_id] = int(msg.get("date", time.time()) * 1000)
                except Exception as exc:
                    # Retry once without markdown if markdown parsing failed
                    try:
                        payload.pop("parse_mode", None)
                        data = json.dumps(payload).encode("utf-8")
                        req_plain = urllib.request.Request(
                            f"{self.base_url}/sendMessage",
                            data=data,
                            headers={"Content-Type": "application/json"}
                        )
                        with urllib.request.urlopen(req_plain, timeout=15, context=self.ssl_context) as resp:
                            res = json.loads(resp.read().decode("utf-8"))
                            if res.get("ok"):
                                msg = res.get("result", {})
                                msg_id = str(msg.get("message_id"))
                                sent[msg_id] = int(msg.get("date", time.time()) * 1000)
                    except Exception as inner_exc:
                        logging.error("Failed to send telegram message: %s", inner_exc)
        return sent


def check_telegram(bot_token):
    """Check Telegram bot token validity via getMe."""
    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                user = data.get("result", {})
                return {"ok": True, "bot_username": user.get("username"), "first_name": user.get("first_name")}
            return {"ok": False, "code": data.get("description", "invalid_token")}
    except Exception as exc:
        return {"ok": False, "code": str(exc)}


def run(config, api, store):
    from .bridge import Bridge

    sender = TelegramSender(config["telegram_bot_token"])
    bridge = Bridge(api, store, sender, config.get("allowed_user_ids", []))
    pair_code = bridge.enable_pairing()

    print("=" * 60)
    print("Mika Telegram Connector is running!")
    if pair_code:
        print("\n[IMPORTANT] First pairing required:")
        print(f"Send this command to your Telegram bot within 10 minutes:")
        print(f"  /pair {pair_code}")
        print("Only the paired user can submit tasks to your phone.")
    else:
        print(f"Allowed users: {list(bridge.owners())}")
    print("=" * 60, flush=True)

    stop = threading.Event()

    def work():
        try:
            bridge.recover()
        except Exception as exc:
            logging.error("Recovery failed: %s", exc)
        while not stop.is_set():
            try:
                if not bridge.work_once():
                    time.sleep(0.5)
            except Exception as exc:
                logging.error("Worker error: %s", exc)
                time.sleep(2)

    def poller():
        while not stop.is_set():
            try:
                bridge.poll_once()
            except Exception as exc:
                logging.error("Poller error: %s", exc)
            time.sleep(2)

    worker_thread = threading.Thread(target=work, daemon=True, name="mika-tele-worker")
    poller_thread = threading.Thread(target=poller, daemon=True, name="mika-tele-poller")
    worker_thread.start()
    poller_thread.start()

    # Long polling updates from Telegram
    offset = 0
    poll_url_base = f"https://api.telegram.org/bot{config['telegram_bot_token']}/getUpdates"
    ssl_context = ssl.create_default_context()

    try:
        while not stop.is_set():
            try:
                url = f"{poll_url_base}?offset={offset}&timeout=20"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for u in updates:
                            update_id = u["update_id"]
                            offset = max(offset, update_id + 1)
                            bridge.receive(u)
                    else:
                        time.sleep(2)
            except Exception as exc:
                time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping Mika Telegram connector...")
    finally:
        stop.set()
        worker_thread.join(timeout=2)
        poller_thread.join(timeout=2)
