"""Portable research notes and an explicit, opt-in local Obsidian publisher.

Reading configuration and building previews never enumerates or reads a vault.
The only vault mutation is publish(), which requires a matching preview token.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import math
import os
import re
import secrets
import threading
import zipfile
from html import escape
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from backend.services.errors import ResearchError

_SECRET = secrets.token_bytes(32)
_LOCK = threading.RLock()
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)
_PRIVATE_KEYS = {"vault_path", "local_path", "root", "data_dir", "cache_dir", "file_path", "path"}
DEFAULT_CONFIG = {"enabled": False, "vault_path": "", "folder": "QuantSandbox"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def _redact(value):
    if isinstance(value, dict):
        return {str(k): _redact(v) for k, v in value.items() if str(k).lower() not in _PRIVATE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        if value.startswith(("/", "\\\\", "file://")):
            return "[local path omitted]"
        value = re.sub(r"\b[A-Za-z]:[\\/][^\r\n\"<>]*", "[local path omitted]", value)
        value = re.sub(r"(?:file://|\\\\)[^\s\r\n\"<>]+", "[local path omitted]", value)
        return re.sub(r"(?<![\w:])/(?:Users|home|tmp|private|var|mnt|media|Volumes|data|opt|root|etc|srv)/[^\s\r\n\"<>]+", "[local path omitted]", value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _linked(path: Path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _check_chain(path: Path):
    for parent in [*reversed(path.parents), path]:
        if _linked(parent):
            raise ResearchError(422, "目标路径不能包含符号链接或目录联接")


def _relative_folder(value):
    text = str(value).replace("\\", "/")
    if not text:
        return ""
    parts = text.split("/")
    if text.startswith("/") or any(
        part in {"", ".", ".."} or part.startswith(".") or part.endswith((".", " "))
        or _RESERVED.match(part) or re.search(r'[<>:"|?*\x00-\x1f]', part)
        for part in parts
    ):
        raise ResearchError(422, "笔记子目录必须为安全的相对路径，不能使用隐藏目录或上级目录")
    return "/".join(parts)


def _slug(value):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(value)).strip(" .")[:70]
    if not text or _RESERVED.match(text):
        text = "研究记录"
    return text


def _number(value):
    if value is None:
        return "缺失 / 未定义"
    return f"{value:,.6g}" if isinstance(value, (int, float)) else str(value)


def _line_svg(title, rows, key, unit):
    valid = [(i, r.get(key)) for i, r in enumerate(rows) if isinstance(r.get(key), (int, float)) and math.isfinite(r[key])]
    if not valid:
        return None
    lo, hi = min(v for _, v in valid), max(v for _, v in valid)
    span = hi - lo or max(abs(hi) * .05, 1)
    commands, previous = [], None
    for i, value in valid:
        commands.append(f'{"L" if previous == i - 1 else "M"}{75 + i * 820 / max(1, len(rows) - 1):.2f},{320 - (value - lo) * 230 / span:.2f}')
        previous = i
    first, last = rows[0].get("date", ""), rows[-1].get("date", "")
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="420" viewBox="0 0 960 420"><rect width="960" height="420" fill="white"/><g fill="#243c42" font-family="sans-serif"><text x="40" y="35" font-size="20">{escape(title)}</text><text x="40" y="65" font-size="12">{escape(unit)}；范围 {lo:.6g} — {hi:.6g}；缺失不连线</text><path d="{" ".join(commands)}" stroke="#087d79" stroke-width="2" fill="none"/><text x="75" y="355">{escape(str(first))}</text><text x="810" y="355">{escape(str(last))}</text><text x="40" y="395" font-size="12">QuantSandbox · 来源、参数与冻结快照标识见同目录附件</text></g></svg>'


class ObsidianService:
    def __init__(self, root: Path, research_get=None, simulation_get=None):
        self.root = Path(root)
        self.config_path = self.root / ".local" / "obsidian.json"
        self.research_get = research_get
        self.simulation_get = simulation_get

    def config(self):
        if not self.config_path.exists():
            return dict(DEFAULT_CONFIG)
        try:
            result = json.loads(self.config_path.read_text(encoding="utf-8"))
            return {key: result.get(key, value) for key, value in DEFAULT_CONFIG.items()}
        except (OSError, ValueError) as exc:
            raise ResearchError(409, "Obsidian 本地配置无法读取，请重新保存配置") from exc

    def save_config(self, value):
        selected = {**DEFAULT_CONFIG, **value}
        selected["enabled"] = bool(selected["enabled"])
        selected["folder"] = _relative_folder(selected["folder"])
        selected["vault_path"] = str(selected["vault_path"]).strip()
        if selected["enabled"] and not selected["vault_path"]:
            raise ResearchError(422, "启用写入前请选择本机笔记库目录")
        if selected["vault_path"]:
            self._vault(selected)
        with _LOCK:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.config_path.with_suffix(".tmp")
            temp.write_text(_json(selected), encoding="utf-8")
            os.replace(temp, self.config_path)
        return selected

    def _vault(self, config):
        text = config["vault_path"]
        path = Path(text)
        if not path.is_absolute() or text.startswith(("\\\\", "//")) or "://" in text:
            raise ResearchError(422, "笔记库必须是已存在的本机绝对目录，不能使用网络路径")
        _check_chain(path)
        if not path.is_dir():
            raise ResearchError(422, "笔记库目录不存在")
        return path.resolve()

    def _record(self, request):
        identifier, kind = request["run_id"], request["kind"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            raise ResearchError(422, "研究记录编号无效")
        try:
            if kind == "research":
                if self.research_get:
                    return self.research_get(identifier)
                from backend.workbench import store
                run = store.get_run(identifier)
                if not run.get("sources"):
                    run["sources"] = [{k: v for k, v in s.items() if k not in {"rows", "raw"}} for s in store.get_snapshots(run.get("inputs", []))]
                return run
            if kind == "simulation" and self.simulation_get:
                run = self.simulation_get(identifier)
                if run.get("status") != "completed":
                    raise ResearchError(409, "请等待模拟实验完成后导出")
                return run
        except ValueError as exc:
            raise ResearchError(404, "研究记录不存在") from exc
        raise ResearchError(422, "不支持的研究记录类型")

    def _build(self, request):
        run = _redact(self._record(request))
        title = _redact(request.get("title") or run.get("title") or run.get("name") or "研究记录")
        title = title.replace("\r", " ").replace("\n", " ")
        kind, identifier = request["kind"], request["run_id"]
        stem = f"{_slug(title)}-{kind}-{identifier[:12]}"
        filename, assets = stem + ".md", stem + ".assets"
        params = run.get("params", run.get("config", {}))
        result = run.get("result", {})
        version = run.get("version") or ((result.get("engine") or {}).get("version", "unknown") if isinstance(result, dict) else "unknown")
        sources = run.get("sources", []) if kind == "research" else run.get("manifest", [])
        source_hashes = run.get("inputs", []) if kind == "research" else [s.get("sha256") for s in sources]
        body = f'---\napplication: QuantSandbox\nrecord_kind: {kind}\nrecord_id: {_json(identifier)}\ntitle: {_json(title)}\ncreated: {_json(run.get("created_at", ""))}\n---\n\n# {title}\n\n'
        body += f'记录类型：{kind} / {run.get("kind", "")}；版本：{version}。\n\n'
        if kind == "simulation" and (run.get("synthetic") or params.get("source") == "demo" or any(source.get("synthetic") for source in sources)):
            body += "数据性质：合成演示行情，非真实市场价格；用于操作演示与模型检验，不作为真实市场研究结论。\n\n"
        if request.get("notes"):
            body += "## 研究备注\n\n" + _redact(request["notes"]) + "\n\n"
        body += "## 结果摘要\n\n"
        if isinstance(result, dict):
            if run.get("kind") == "statistics":
                body += f'相关系数：{_number(result.get("correlation"))}；配对样本 n={_number(result.get("n"))}。\n\n'
                condition = result.get("conditional") or {}
                if condition:
                    body += f'条件上涨概率：{_number(condition.get("probability"))}（0—1）；条件样本 n={_number(condition.get("n"))}；基准概率 {_number(condition.get("baseline"))}；基准样本 n={_number(condition.get("baseline_n"))}；95% Wilson 区间 {condition.get("interval")}。\n\n'
            metrics = result.get("metrics") or result.get("baseline") or {}
            if metrics:
                body += "模拟指标：收益率与回撤为百分数，金额为元；null 表示未定义。\n\n```json\n" + _json(metrics) + "\n```\n\n"
            for key, label in (("research_asof", "研究截止日"), ("asof", "数据截止日"), ("method", "计算口径"), ("coverage_note", "覆盖口径"), ("interpretation", "解释"), ("notice", "说明")):
                if result.get(key):
                    body += f"{label}：{result[key]}\n\n"
            if result.get("latest"):
                body += "最新观测（原单位与有效样本数一并保留）：\n\n```json\n" + _json(result["latest"]) + "\n```\n\n"
            if result.get("assumptions"):
                body += "模型假设：\n\n" + "\n".join(f"- {x}" for x in result["assumptions"]) + "\n\n"
        else:
            body += "财务比较结果按原始单位保存于结果附件；单季流量与时点指标分开，缺失值保留。\n\n"
        files = {f"{assets}/parameters.json": _json(params).encode("utf-8"),
                 f"{assets}/sources.json": _json({"snapshots": source_hashes, "sources": sources}).encode("utf-8"),
                 f"{assets}/result.json": _json(result).encode("utf-8"),
                 f"{assets}/recipe.json": _json({"application": "QuantSandbox", "kind": kind, "run_id": identifier,
                     "record_kind": run.get("kind"), "version": version,
                     "created_at": run.get("created_at"), "params": params, "inputs": source_hashes,
                     "replay": f"python -m backend.workbench.cli replay {identifier}" if kind == "research" else f"GET /api/runs/{identifier}/export -> original evidence JSON -> POST /api/import"}).encode("utf-8")}
        body += "## 来源与时间\n\n"
        seen = set()
        for source in sources:
            source = source if isinstance(source, dict) else {"source": str(source)}
            # Bridge manifests wrap the actual upstream provider in origin.
            # Keep the full manifest in sources.json; expose upstream citations here.
            origin = source.get("origin")
            if isinstance(origin, dict):
                source = {**source, **origin}
            name = str(source.get("source") or source.get("name") or source.get("ticker") or "数据来源")
            url = str(source.get("source_url", ""))
            try:
                parsed = urlsplit(url)
                safe_url = parsed.scheme in {"http", "https"} and parsed.netloc and not re.search(r"[\s<>]", url)
            except ValueError:
                safe_url = False
            link = f"[{name.replace('[', '').replace(']', '')}]({url.replace(')', '%29').replace('(', '%28')})" if safe_url else name
            description = (link, source.get("method"), source.get("unit"), source.get("price_basis"), source.get("volume_unit"), source.get("notice"))
            if description in seen:
                continue
            seen.add(description)
            body += f'- {link}；获取 {source.get("fetched_at") or source.get("created_at", "未知")}；单位 {source.get("unit") or source.get("volume_unit", "见附件")}；口径 {source.get("method") or source.get("price_basis", "见附件")}。\n'
            if source.get("notice"):
                body += f'  数据说明：{source["notice"]}\n'
        body += f'\n冻结输入共 {len(source_hashes)} 个；每个输入标识、哈希、请求与获取时间见 [来源附件](<{assets}/sources.json>)。统计期末、公告可用日与抓取时间分别保留，不将当前修订数据视为历史时点数据。\n\n'
        body += "## 参数\n\n```json\n" + _json(params) + "\n```\n\n"
        charts = self._charts(run, title, kind)
        for name, svg in charts.items():
            files[f"{assets}/{name}"] = svg.encode("utf-8")
            body += f'![{title}](<{assets}/{name}>)\n\n'
        body += f'[完整结果](<{assets}/result.json>) · [计算参数](<{assets}/parameters.json>) · [复算入口](<{assets}/recipe.json>)\n\n由 QuantSandbox 手动导出；该文件可单独保管，也可复制到任意 Obsidian 笔记库。\n'
        files = {filename: body.encode("utf-8"), **files}
        return {"kind": kind, "run_id": identifier, "title": title, "filename": filename, "markdown": body}, files

    def _charts(self, run, title, kind):
        result, charts = run.get("result", {}), {}
        if kind == "simulation":
            svg = _line_svg(title + " · 账户净值", result.get("series", []), "equity", "元 CNY")
            if svg:
                charts["equity.svg"] = svg
        elif run.get("kind") in {"national", "etf", "finance"}:
            from backend.workbench import national, etf, service
            if run["kind"] == "national":
                charts = {"footprints.svg": national.chart_svg(run), "financing.svg": national.chart_svg(run, True)}
            elif run["kind"] == "etf":
                charts = {"shares.svg": etf.chart_svg(run, "delta"), "flow.svg": etf.chart_svg(run, "flow")}
            else:
                svg = service.financial_svg(run)
                if svg:
                    charts["finance.svg"] = svg
        elif run.get("kind") == "statistics":
            svg = _line_svg(title + " · X 序列", result.get("points", []), "x", "变换后 X；原口径见参数")
            if svg:
                charts["statistics.svg"] = svg
        return {name: svg.replace("report.md / recipe.json / daily.csv", "笔记与 parameters.json / result.json")
                .replace("report.md / recipe.json", "笔记与 parameters.json")
                .replace("；快照随附", "；冻结输入标识见 sources.json") for name, svg in charts.items()}

    def _token(self, files, config):
        digest = hashlib.sha256(_json(config).encode("utf-8"))
        for path, content in files.items():
            digest.update(path.encode("utf-8"))
            digest.update(hashlib.sha256(content).digest())
        return hmac.new(_SECRET, digest.digest(), hashlib.sha256).hexdigest()

    def preview(self, request):
        note, files = self._build(request)
        config = self.config()
        return {**note, "files": [{"path": path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()} for path, content in files.items()],
                "preview_token": self._token(files, config), "can_publish": bool(config["enabled"] and config["vault_path"]),
                "settings": {"enabled": config["enabled"], "folder": config["folder"]}}

    def export(self, request):
        _, files = self._build(request)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, content in files.items():
                archive.writestr(path, content)
        return output.getvalue()

    def publish(self, request):
        with _LOCK:
            config = self.config()
            if not config["enabled"]:
                raise ResearchError(409, "Obsidian 写入未启用；仍可下载 Markdown 附件包")
            note, files = self._build(request)
            token = request.get("preview_token", "")
            if not token or not hmac.compare_digest(token, self._token(files, config)):
                raise ResearchError(409, "预览已变化或失效，请先重新预览再写入")
            vault = self._vault(config)
            relative = _relative_folder(config["folder"])
            folder = vault.joinpath(*PurePosixPath(relative).parts)
            targets = [folder.joinpath(*PurePosixPath(name).parts) for name in files]
            for target in targets:
                _check_chain(target)
                if not target.resolve().is_relative_to(vault):
                    raise ResearchError(422, "目标文件超出所选笔记库")
                if target.exists():
                    raise ResearchError(409, "目标笔记或附件已存在，请更改标题后重新预览；不会覆盖文件")
            created_files, created_dirs = [], []
            try:
                for target, content in zip(targets, files.values()):
                    parents = []
                    parent = target.parent
                    while not parent.exists():
                        parents.append(parent)
                        parent = parent.parent
                    for directory in reversed(parents):
                        _check_chain(directory)
                        directory.mkdir()
                        created_dirs.append(directory)
                    _check_chain(target)
                    with target.open("xb") as handle:
                        created_files.append(target)
                        handle.write(content)
            except (OSError, ResearchError) as exc:
                for path in reversed(created_files):
                    path.unlink(missing_ok=True)
                for path in reversed(created_dirs):
                    try:
                        path.rmdir()
                    except OSError:
                        pass
                if isinstance(exc, ResearchError):
                    raise
                raise ResearchError(409, "笔记写入失败，已撤回本次创建的文件；未覆盖已有内容") from exc
            return {"published": True, "filename": note["filename"],
                    "files": [target.relative_to(vault).as_posix() for target in targets]}
