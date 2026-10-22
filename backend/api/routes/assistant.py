"""Validated local research command previews."""
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from backend.api.schemas import AssistantRequest, RunConfig

router = APIRouter(prefix="/api", tags=["assistant"])


@router.post("/assistant/plan")
def assistant_plan(request: AssistantRequest):
    from backend.assistant import plan_research

    try:
        result = plan_research(request.prompt, request.base_config)
        result["config"] = RunConfig.model_validate(result["config"]).model_dump(mode="json")
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, f"研究配置未通过校验：{exc}") from exc
    return result
