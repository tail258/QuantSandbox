"""SQLite persistence, one short-lived connection per transaction."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from backend.core.data_center import canonical_json, utc_now


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "research.sqlite3"
        with self.connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                    progress INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    config TEXT NOT NULL, kind TEXT NOT NULL, parent_id TEXT, branch TEXT,
                    manifest TEXT NOT NULL DEFAULT '[]', result TEXT, error TEXT,
                    experiment TEXT, expected_result TEXT
                );
                CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at DESC);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, cursor INTEGER NOT NULL,
                    revealed INTEGER NOT NULL DEFAULT 0, revealed_at TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY, run_id TEXT, title TEXT NOT NULL, body TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            # sqlite3's context manager commits/rolls back but does not close;
            # explicitly release handles, particularly for Windows workspaces.
            connection.close()

    def create_run(self, config: dict, *, kind="backtest", parent_id=None, branch=None,
                   manifest=None, experiment=None, expected_result=None) -> dict:
        identifier, now = uuid.uuid4().hex, utc_now()
        name = config.get("name") or f"{config['strategy']['name']} · {config['start_date']}"
        with self.connect() as connection:
            connection.execute("""INSERT INTO runs
                (id,name,status,progress,created_at,updated_at,config,kind,parent_id,branch,manifest,experiment,expected_result)
                VALUES (?,?, 'queued',0,?,?,?,?,?,?,?,?,?)""",
                (identifier, name, now, now, canonical_json(config), kind, parent_id,
                 canonical_json(branch) if branch else None, canonical_json(manifest or []),
                 canonical_json(experiment) if experiment else None,
                 canonical_json(expected_result) if expected_result else None))
        return self.get_run(identifier)

    @staticmethod
    def _decode(row) -> dict | None:
        if row is None:
            return None
        output = dict(row)
        for key in ["config", "branch", "manifest", "result", "error", "experiment", "expected_result"]:
            if key in output and output[key] is not None:
                output[key] = json.loads(output[key])
        output["synthetic"] = output["config"].get("source") == "demo"
        return output

    def get_run(self, identifier: str) -> dict | None:
        with self.connect() as connection:
            return self._decode(connection.execute("SELECT * FROM runs WHERE id=?", (identifier,)).fetchone())

    def list_runs(self, limit=100) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        results = []
        for row in rows:
            decoded = self._decode(row)
            result = decoded.pop("result", None)
            decoded["metrics"] = (result or {}).get("metrics", (result or {}).get("baseline"))
            decoded.pop("expected_result", None)
            decoded.pop("experiment", None)
            results.append(decoded)
        return results

    def patch_run(self, identifier: str, *, unless_terminal=False, **changes) -> None:
        permitted = {"status", "progress", "result", "error", "manifest", "name"}
        if not changes.keys() <= permitted:
            raise ValueError("Unsupported database update")
        encoded = {key: canonical_json(value) if key in {"result", "error", "manifest"} else value
                   for key, value in changes.items()}
        encoded["updated_at"] = utc_now()
        assignments = ",".join(f"{key}=?" for key in encoded)
        condition = " AND status NOT IN ('cancelled','failed','completed')" if unless_terminal else ""
        with self.connect() as connection:
            connection.execute(f"UPDATE runs SET {assignments} WHERE id=?{condition}", (*encoded.values(), identifier))

    def recover_interrupted(self) -> None:
        with self.connect() as connection:
            connection.execute("""UPDATE runs SET status='failed',updated_at=?,error=?
                                  WHERE status IN ('queued','running')""",
                               (utc_now(), canonical_json({"code": "interrupted", "message": "服务在研究完成前停止。请重新运行；已完成研究与数据快照仍保留。"})))

    def next_queued(self) -> str | None:
        with self.connect() as connection:
            row = connection.execute("SELECT id FROM runs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        return row[0] if row else None

    def active_count(self) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM runs WHERE status IN ('queued','running')").fetchone()[0]

    def create_session(self, run_id: str, cursor: int) -> dict:
        identifier = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("INSERT INTO sessions (id,run_id,cursor,created_at) VALUES (?,?,?,?)",
                               (identifier, run_id, cursor, utc_now()))
        return self.get_session(identifier)

    def get_session(self, identifier: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id=?", (identifier,)).fetchone()
        return dict(row) if row else None

    def advance_session(self, identifier: str, steps: int, maximum: int, reveal=False) -> dict:
        with self.connect() as connection:
            if reveal:
                connection.execute("UPDATE sessions SET cursor=?,revealed=1,revealed_at=COALESCE(revealed_at,?) WHERE id=?",
                                   (maximum, utc_now(), identifier))
            else:
                connection.execute("UPDATE sessions SET cursor=MIN(cursor+?,?) WHERE id=?", (steps, maximum, identifier))
        return self.get_session(identifier)

    def list_notes(self, run_id=None) -> list[dict]:
        with self.connect() as connection:
            if run_id:
                rows = connection.execute("SELECT * FROM notes WHERE run_id=? ORDER BY updated_at DESC", (run_id,)).fetchall()
            else:
                rows = connection.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def save_note(self, title, body, run_id=None, identifier=None) -> dict:
        identifier, now = identifier or uuid.uuid4().hex, utc_now()
        with self.connect() as connection:
            connection.execute("""INSERT INTO notes VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                                  run_id=excluded.run_id,title=excluded.title,body=excluded.body,updated_at=excluded.updated_at""",
                               (identifier, run_id, title, body, now, now))
            return dict(connection.execute("SELECT * FROM notes WHERE id=?", (identifier,)).fetchone())

    def delete_note(self, identifier) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM notes WHERE id=?", (identifier,))
        return cursor.rowcount > 0
