import json
import os
import sqlite3
import threading
from pathlib import Path


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        if os.name != "nt":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS owners(id TEXT PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sessions(peer TEXT PRIMARY KEY, conversation TEXT, task_id TEXT,
            uncertain INTEGER NOT NULL DEFAULT 0, notice TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS questions(peer TEXT PRIMARY KEY, task_id TEXT NOT NULL,
            notice TEXT NOT NULL, message_ids TEXT NOT NULL, shown_at_ms INTEGER);
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(questions)")}
        if "shown_at_ms" not in columns:
            self.db.execute("ALTER TABLE questions ADD COLUMN shown_at_ms INTEGER")
        self.db.commit()

    def execute(self, sql, params=()):
        with self.lock:
            cursor = self.db.execute(sql, params)
            rows = cursor.fetchall()
            self.db.commit()
            return rows

    def enqueue(self, event):
        with self.lock:
            cursor = self.db.execute("INSERT OR IGNORE INTO inbox VALUES(?,?,'pending')",
                                     (event["id"], json.dumps(event, ensure_ascii=False)))
            self.db.commit()
            return cursor.rowcount == 1

    def pop(self):
        with self.lock:
            row = self.db.execute("SELECT * FROM inbox WHERE state='pending' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                return None
            self.db.execute("UPDATE inbox SET state='processing' WHERE id=?", (row["id"],))
            self.db.commit()
            return json.loads(row["payload"])

    def session(self, peer):
        self.execute("INSERT OR IGNORE INTO sessions(peer) VALUES(?)", (peer,))
        return dict(self.execute("SELECT * FROM sessions WHERE peer=?", (peer,))[0])

    def update(self, peer, **values):
        assert set(values) <= {"conversation", "task_id", "uncertain", "notice"}
        self.session(peer)
        self.execute("UPDATE sessions SET " + ",".join(k + "=?" for k in values) + " WHERE peer=?",
                     (*values.values(), peer))

    def question(self, peer, task_id, notice):
        row = self.execute("SELECT message_ids, shown_at_ms FROM questions WHERE peer=? AND task_id=? AND notice=?",
                           (peer, task_id, notice))
        if not row:
            return None
        return set(json.loads(row[0]["message_ids"])), row[0]["shown_at_ms"]

    def remember_question(self, peer, task_id, notice, message_ids):
        ids = list(message_ids.keys()) if isinstance(message_ids, dict) else list(message_ids)
        shown_at = max(message_ids.values()) if isinstance(message_ids, dict) and message_ids else None
        self.execute("INSERT OR REPLACE INTO questions VALUES(?,?,?,?,?)",
                     (peer, task_id, notice, json.dumps(ids), shown_at))
