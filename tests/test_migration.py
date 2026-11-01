import importlib.util
from pathlib import Path
import sqlite3

import pytest

spec = importlib.util.spec_from_file_location("import_research", Path(__file__).parents[1] / "scripts" / "import_research.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_research_copy_preserves_source_and_excludes_external_helpers(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    data = source / "data"
    data.mkdir(parents=True)
    original = data / "workbench.sqlite"
    with sqlite3.connect(original) as connection:
        for name in ("snapshots", "runs", "profiles"):
            connection.execute(f"CREATE TABLE {name}(id TEXT)")
            connection.execute(f"INSERT INTO {name} VALUES ('frozen')")
    before = original.read_bytes()
    artifacts = data / "companies" / "000001"
    artifacts.mkdir(parents=True)
    (artifacts / "source.txt").write_text("public report", encoding="utf-8")
    (artifacts / "handoff.json").write_text("private destination", encoding="utf-8")
    (artifacts / "helper.py").write_text("external write", encoding="utf-8")
    result = module.migrate(source, target)
    assert result["counts"] == {"snapshots": 1, "runs": 1, "profiles": 1}
    assert result["copied_artifacts"] == 1
    assert result["excluded_helpers"] == 2
    assert original.read_bytes() == before
    assert (target / "data/workbench/companies/000001/source.txt").read_text() == "public report"
    assert not (target / "data/workbench/companies/000001/handoff.json").exists()
    with pytest.raises(ValueError, match="已存在"):
        module.migrate(source, target)
    with pytest.raises(ValueError, match="独立目录"):
        module.migrate(source, source / "nested")
