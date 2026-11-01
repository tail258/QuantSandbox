"""Copy a legacy research workspace into this workspace without changing its files."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[1]


def migrate(source: Path, destination: Path = ROOT) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("源工作区和目标工作区必须为独立目录")
    original = source / "data" / "workbench.sqlite"
    if not original.is_file():
        raise ValueError("源目录没有 data/workbench.sqlite")
    target = destination / "data" / "workbench"
    if target.exists():
        raise ValueError("目标研究数据目录已存在；不会覆盖，请使用独立目标目录")
    staging = destination / ".local" / ("research-import-" + uuid.uuid4().hex)
    staging.mkdir(parents=True)
    database = staging / "workbench.sqlite"
    try:
        # A read-only SQLite connection plus backup captures committed WAL data.
        # Copying the main file alone would lose active transactions.
        with closing(sqlite3.connect(original.as_uri() + "?mode=ro", uri=True)) as reader:
            with closing(sqlite3.connect(database)) as writer:
                reader.backup(writer)
                check = writer.execute("PRAGMA integrity_check").fetchone()[0]
                if check != "ok":
                    raise ValueError("源数据库完整性检查失败")
                counts = {table: writer.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                          for table in ("snapshots", "runs", "profiles")}
        copied, excluded = 0, 0
        # Only research artifacts. Never copy a vault, executable helper scripts,
        # handoff files, old server PIDs, logs, or in-flight job state.
        for directory in ("companies", "national"):
            origin = source / "data" / directory
            if not origin.exists():
                continue
            for path in origin.rglob("*"):
                if not path.is_file():
                    continue
                name = path.name.lower()
                if path.is_symlink() or path.suffix.lower() in {".py", ".ps1", ".cmd", ".bat"} or any(
                    token in name for token in ("handoff", "obsidian", "__pycache__")
                ) or "__pycache__" in path.parts:
                    excluded += 1
                    continue
                resolved = path.resolve()
                if source not in resolved.parents:
                    raise ValueError("研究附件超出源工作区")
                output = staging / directory / path.relative_to(origin)
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, output)
                copied += 1
        manifest = {"format": "quantsandbox-research-import-v1", "counts": counts,
                    "copied_artifacts": copied, "excluded_helpers": excluded,
                    "database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
                    "source_modified": False,
                    "notice": "保留原始快照与记录编号；未导入私人笔记库或外部写入脚本。"}
        (staging / "migration.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(target)
        return manifest
    except BaseException:
        # Leave failed staging in .local for diagnosis; never touch the source.
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="只读复制旧研究工作区数据，目标存在则拒绝覆盖")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.destination), ensure_ascii=False, indent=2))
