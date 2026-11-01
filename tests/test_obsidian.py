import copy
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.api.routes.obsidian import router
from backend.integrations.obsidian import ObsidianService
from backend.services.errors import ResearchError


REQUEST = {"kind": "research", "run_id": "abc123", "notes": "核对来源后记录。"}
RESEARCH = {
    "id": "abc123", "kind": "statistics", "title": "库存与价格", "version": "3.0.0",
    "created_at": "2026-11-01T01:00:00+00:00", "inputs": ["source123"],
    "params": {"start": "2025-01-01", "end": "2026-10-28", "lag": 5, "frequency": "D"},
    "sources": [{"source": "公开统计", "source_url": "https://example.org/source", "fetched_at": "2026-10-29T01:00:00Z", "unit": "吨", "method": "按实际可用日对齐"}],
    "result": {"correlation": .42, "n": 123, "conditional": {"n": 20, "probability": .6, "baseline_n": 40, "baseline": .5, "interval": [.38, .78]},
               "points": [{"date": "2026-10-27", "x": 1}, {"date": "2026-10-28", "x": 2}], "method": "缺失保留"}}


def make_service(root, record=None):
    return ObsidianService(root, research_get=lambda _: copy.deepcopy(record or RESEARCH))


def test_disabled_preview_and_portable_export_never_create_or_read_vault(tmp_path, monkeypatch):
    root = tmp_path / "state"
    service = make_service(root)
    assert service.config() == {"enabled": False, "vault_path": "", "folder": "QuantSandbox"}
    preview = service.preview(REQUEST)
    assert not preview["can_publish"]
    assert not root.exists()
    with pytest.raises(ResearchError, match="未启用"):
        service.publish({**REQUEST, "preview_token": preview["preview_token"]})
    assert not root.exists()
    with zipfile.ZipFile(io.BytesIO(service.export(REQUEST))) as archive:
        names = archive.namelist()
        assert any(name.endswith(".md") for name in names)
        assert any(name.endswith(".svg") for name in names)
        text = archive.read(preview["filename"]).decode("utf-8")
        assert text == preview["markdown"]
        assert "https://example.org/source" in text and "2026-10-29" in text and "吨" in text
        assert "n=123" in text and "n=20" in text and '"lag": 5' in text
        metadata = json.loads(archive.read(next(n for n in names if n.endswith("sources.json"))))
        assert metadata["snapshots"] == ["source123"]
        assert all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in names)


def test_config_and_preview_do_not_scan_vault_and_explicit_publish_matches_preview(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    existing = vault / "Existing.md"
    existing.write_text("private original", encoding="utf-8")
    service = make_service(tmp_path / "state")
    service.save_config({"enabled": True, "vault_path": str(vault), "folder": "Research/Observations"})
    assert list(vault.iterdir()) == [existing]
    original_read = Path.read_text
    def read_without_vault(path, *args, **kwargs):
        assert not path.is_relative_to(vault)
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_without_vault)
    preview = service.preview(REQUEST)
    assert preview["can_publish"]
    assert list(vault.iterdir()) == [existing]
    result = service.publish({**REQUEST, "preview_token": preview["preview_token"]})
    assert result["published"]
    with (vault / result["files"][0]).open(encoding="utf-8") as file:
        assert file.read() == preview["markdown"]
    assert existing.read_bytes() == b"private original"
    with pytest.raises(ResearchError, match="已存在"):
        service.publish({**REQUEST, "preview_token": preview["preview_token"]})
    assert existing.read_bytes() == b"private original"


@pytest.mark.parametrize("folder", ["../notes", "/notes", "C:/notes", "a/../b", "a//b", ".obsidian", "a/.obsidian", "CON", "notes.", "notes ", "a\\..\\b"])
def test_unsafe_folders_rejected_before_any_write(tmp_path, folder):
    with pytest.raises(ResearchError):
        make_service(tmp_path / "state").save_config({"enabled": False, "folder": folder})
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("vault_path", ["relative/path", "https://host/vault", "//host/share", "\\\\host\\share"])
def test_nonlocal_vaults_rejected(tmp_path, vault_path):
    with pytest.raises(ResearchError):
        make_service(tmp_path / "state").save_config({"enabled": True, "vault_path": vault_path})


def test_publish_requires_current_preview_after_notes_or_config_change(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    service = make_service(tmp_path / "state")
    service.save_config({"enabled": True, "vault_path": str(vault)})
    preview = service.preview(REQUEST)
    with pytest.raises(ResearchError, match="重新预览"):
        service.publish({**REQUEST, "notes": "new", "preview_token": preview["preview_token"]})
    service.save_config({"enabled": True, "vault_path": str(vault), "folder": "Changed"})
    with pytest.raises(ResearchError, match="重新预览"):
        service.publish({**REQUEST, "preview_token": preview["preview_token"]})
    assert not list(vault.iterdir())


def test_no_overwrite_conflicts_leave_no_partial_files(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    service = make_service(tmp_path / "state")
    service.save_config({"enabled": True, "vault_path": str(vault)})
    preview = service.preview(REQUEST)
    collision = vault / "QuantSandbox" / preview["files"][-1]["path"]
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"existing")
    before = set(vault.rglob("*"))
    with pytest.raises(ResearchError, match="已存在"):
        service.publish({**REQUEST, "preview_token": preview["preview_token"]})
    assert set(vault.rglob("*")) == before and collision.read_bytes() == b"existing"


def test_symlinked_target_rejected_without_touching_outside(tmp_path):
    vault, outside = tmp_path / "vault", tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    link = vault / "QuantSandbox"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("Creating symlinks requires local privileges on this OS")
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
        assert link.is_junction()
    try:
        service = make_service(tmp_path / "state")
        service.save_config({"enabled": True, "vault_path": str(vault)})
        preview = service.preview(REQUEST)
        with pytest.raises(ResearchError, match="链接|联接"):
            service.publish({**REQUEST, "preview_token": preview["preview_token"]})
        assert not list(outside.iterdir())
    finally:
        if link.is_symlink():
            link.unlink()
        else:
            link.rmdir()


def test_failed_write_rolls_back_only_new_files(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    old = vault / "Unrelated.md"
    old.write_bytes(b"private original")
    service = make_service(tmp_path / "state")
    service.save_config({"enabled": True, "vault_path": str(vault)})
    preview = service.preview(REQUEST)
    original_open = Path.open
    def failing_open(path, mode="r", *args, **kwargs):
        if path.suffix == ".svg" and mode == "xb":
            raise OSError("simulated disk error")
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(ResearchError, match="撤回"):
        service.publish({**REQUEST, "preview_token": preview["preview_token"]})
    assert list(vault.iterdir()) == [old]
    assert old.read_bytes() == b"private original"


def test_portable_export_omits_private_paths_and_preserves_original_missing(tmp_path):
    record = copy.deepcopy(RESEARCH)
    record["params"]["root"] = str(tmp_path / "private")
    record["params"]["notes"] = "local D:\\Private\\Notes\\secret.md"
    record["result"]["correlation"] = None
    record["result"]["source_file"] = str(tmp_path / "private" / "record.csv")
    record["result"]["embedded"] = "location \\\\server\\private\\notes.md and file:///home/private/note"
    record["result"]["embedded_posix"] = "location /home/private/notes.md"
    service = make_service(tmp_path / "state", record)
    with zipfile.ZipFile(io.BytesIO(service.export(REQUEST))) as archive:
        text = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist())
        assert str(tmp_path) not in text and "D:\\Private" not in text
        assert "server" not in text and "/home/private" not in text
        result = json.loads(archive.read(next(name for name in archive.namelist() if name.endswith("result.json"))))
        assert result["correlation"] is None


def test_api_contract_download_preview_and_manual_publish(tmp_path):
    from types import SimpleNamespace
    app = FastAPI()
    app.include_router(router)
    app.state.store = SimpleNamespace(root=tmp_path / "state")
    simulation = {"id": "simulation1", "status": "completed", "kind": "backtest", "name": "合成演示",
                  "created_at": "2026-11-01", "config": {"source": "demo"}, "manifest": [{"source": "demo", "sha256": "abc", "volume_unit": "shares"}],
                  "result": {"metrics": {"total_return": 1.2}, "series": [{"date": "2026-01-01", "equity": 1000}, {"date": "2026-01-02", "equity": 1012}], "engine": {"version": "3.0.0"}}}
    app.state.research = SimpleNamespace(require_run=lambda identifier, completed: simulation)
    @app.exception_handler(ResearchError)
    async def handler(request: Request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)
    with TestClient(app) as client:
        assert client.get("/api/obsidian/config").json()["enabled"] is False
        request = {"kind": "simulation", "run_id": "simulation1"}
        preview = client.post("/api/obsidian/preview", json=request).json()
        assert preview["preview_token"] and not preview["can_publish"]
        assert "合成演示行情" in preview["markdown"]
        export = client.post("/api/obsidian/export", json=request)
        assert export.status_code == 200 and export.headers["content-type"] == "application/zip"
        assert "simulation1" in export.headers["content-disposition"]
        assert client.post("/api/obsidian/publish", json={**request, "preview_token": preview["preview_token"]}).status_code == 409
        assert not (tmp_path / "state").exists()


def test_simulation_origin_lineage_preserved_and_cited_without_local_paths(tmp_path):
    run = {"id": "simulation2", "status": "completed", "kind": "backtest", "name": "冻结数据实验",
           "config": {"source": "snapshot"}, "manifest": [{"source": "snapshot", "sha256": "fullhash", "price_basis": "raw_unadjusted", "volume_unit": "shares",
                "origin": {"module": "research", "snapshot_id": "research123", "snapshot_sha256": "originhash", "source": "公开行情源",
                           "source_url": "https://example.org/prices", "fetched_at": "2026-10-29", "method": "不复权日线；成交量统一为股",
                           "request": {"adjust": "3", "root": str(tmp_path / "private")}}}],
           "result": {"metrics": {"total_return": 1.2}, "series": [{"date": "2026-01-01", "equity": 1000}, {"date": "2026-01-02", "equity": 1012}], "engine": {"version": "3.0.0"}}}
    service = ObsidianService(tmp_path / "state", simulation_get=lambda _: run)
    request = {"kind": "simulation", "run_id": "simulation2"}
    preview = service.preview(request)
    assert "https://example.org/prices" in preview["markdown"]
    assert "不复权日线" in preview["markdown"] and "2026-10-29" in preview["markdown"]
    assert "合成演示行情" not in preview["markdown"]
    with zipfile.ZipFile(io.BytesIO(service.export(request))) as archive:
        raw = archive.read(next(name for name in archive.namelist() if name.endswith("sources.json")))
        metadata = json.loads(raw)
        assert metadata["sources"][0]["origin"]["snapshot_sha256"] == "originhash"
        assert metadata["sources"][0]["origin"]["request"] == {"adjust": "3"}
        assert str(tmp_path).encode() not in raw


def test_full_app_research_export_respects_app_scoped_store(tmp_path):
    from backend.main import create_app
    with TestClient(create_app(tmp_path / "isolated", run_jobs=False)) as client:
        text = "date,value,available_date\n" + "\n".join(f"2026-01-{i:02}, {i * i},2026-01-{i:02}" for i in range(1, 25))
        imported = client.post("/api/research/import", json={"text": text, "meta": {
            "symbol": "obsidian-test", "name": "观察指标", "source": "公开原文", "source_url": "https://example.org/observations",
            "unit": "吨", "method": "按实际可用日对齐"}})
        assert imported.status_code == 200, imported.text
        sid = imported.json()["id"] + ":value"
        saved = client.post("/api/research/analyze", json={"x": sid, "y": sid, "start": "2026-01-01", "end": "2026-01-24", "frequency": "D", "transform": "diff", "lag": 0})
        assert saved.status_code == 200, saved.text
        request = {"kind": "research", "run_id": saved.json()["id"]}
        preview = client.post("/api/obsidian/preview", json=request)
        assert preview.status_code == 200, preview.text
        assert "https://example.org/observations" in preview.json()["markdown"]
        assert client.post("/api/obsidian/export", json=request).status_code == 200
        assert not (tmp_path / "isolated" / ".local").exists()
