"""Small cross-module research index; source records remain owned by each module."""
from __future__ import annotations
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from backend.core.data_format import utc_now
from backend.services.errors import ResearchError


class ProjectStore:
    def __init__(self, root: Path):
        self.path = Path(root) / 'projects.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, question TEXT NOT NULL,
                    symbols TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_links (
                    project_id TEXT NOT NULL, kind TEXT NOT NULL, run_id TEXT NOT NULL,
                    linked_at TEXT NOT NULL, PRIMARY KEY(project_id,kind,run_id)
                );
            ''')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def require(self, identifier: str):
        with self.connect() as connection:
            row = connection.execute('SELECT * FROM projects WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise ResearchError(404, '研究项目不存在')
            result = dict(row)
            result['symbols'] = json.loads(result['symbols'])
            result['links'] = [dict(r) for r in connection.execute(
                'SELECT kind,run_id,linked_at FROM project_links WHERE project_id=? ORDER BY linked_at', (identifier,))]
        return result

    def list(self):
        with self.connect() as connection:
            ids = [r[0] for r in connection.execute('SELECT id FROM projects ORDER BY updated_at DESC')]
        return {'projects': [self.require(identifier) for identifier in ids]}

    def create(self, name: str, question: str, symbols: list[str]):
        if not name.strip():
            raise ResearchError(422, '请填写研究项目名称')
        if len(symbols) != len(set(symbols)) or any(not re.fullmatch(r'\d{6}', s) for s in symbols):
            raise ResearchError(422, '证券代码须为不重复的六位数字')
        identifier, now = uuid.uuid4().hex, utc_now()
        with self.connect() as connection:
            connection.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',
                               (identifier, name.strip(), question.strip(), json.dumps(symbols), now, now))
        return self.require(identifier)

    def link(self, identifier: str, kind: str, run_id: str):
        self.require(identifier)
        now = utc_now()
        with self.connect() as connection:
            connection.execute('INSERT OR IGNORE INTO project_links VALUES(?,?,?,?)', (identifier, kind, run_id, now))
            connection.execute('UPDATE projects SET updated_at=? WHERE id=?', (now, identifier))
        return self.require(identifier)
