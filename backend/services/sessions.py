"""Persisted replay sessions and projections of their visible history."""
from backend.api.schemas import AdvanceRequest, SessionRequest
from backend.services.errors import ResearchError
from backend.services.research import ResearchService


class SessionService:
    def __init__(self, research: ResearchService):
        self.research = research
        self.store = research.store

    def session_view(self, identifier: str) -> dict:
        from backend.research import calculate_metrics

        session = self.store.get_session(identifier)
        if session is None:
            raise ResearchError(404, "推演会话不存在")
        run = self.research.require_run(session["run_id"], completed=True, simulation=True)
        result = run["result"]
        series = result["series"]
        cursor = min(session["cursor"], len(series) - 1)
        cutoff = series[cursor]["date"]
        visible_series = [row for row in series if row["date"] <= cutoff]
        visible_trades = [row for row in result["trades"] if row["date"] <= cutoff]
        visible = {"series": visible_series, "trades": visible_trades,
                   "metrics": calculate_metrics(visible_series, visible_trades, run["config"]["account"]["initial_cash"]),
                   "bars": {ticker: [row for row in rows if row["date"] <= cutoff] for ticker, rows in result["bars"].items()},
                   "decisions": [row for row in result["decisions"] if row["date"] <= cutoff],
                   "checkpoints": [row for row in result["checkpoints"] if row["date"] <= cutoff]}
        return {"id": identifier, "run_id": run["id"], "cursor": cursor, "date": cutoff,
                "total_steps": len(series), "revealed": bool(session["revealed"]),
                "revealed_at": session["revealed_at"], "source": run["config"]["source"],
                "synthetic": run["synthetic"], "result": visible}

    def create_session(self, identifier: str, request: SessionRequest):
        run = self.research.require_run(identifier, completed=True, simulation=True)
        if request.cursor >= len(run["result"]["series"]):
            raise ResearchError(422, "推演起点超出研究时间范围")
        session = self.store.create_session(identifier, request.cursor)
        return self.session_view(session["id"])

    def get_session(self, identifier: str):
        return self.session_view(identifier)

    def advance_session(self, identifier: str, request: AdvanceRequest):
        session = self.store.get_session(identifier)
        if session is None:
            raise ResearchError(404, "推演会话不存在")
        run = self.research.require_run(session["run_id"], completed=True, simulation=True)
        self.store.advance_session(identifier, request.steps, len(run["result"]["series"]) - 1)
        return self.session_view(identifier)

    def reveal_session(self, identifier: str):
        session = self.store.get_session(identifier)
        if session is None:
            raise ResearchError(404, "推演会话不存在")
        run = self.research.require_run(session["run_id"], completed=True, simulation=True)
        self.store.advance_session(identifier, 0, len(run["result"]["series"]) - 1, reveal=True)
        return self.session_view(identifier)
