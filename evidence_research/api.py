from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from .evaluation import evaluate_result
from .industry import IndustryRequest, build_industry_prompt
from .providers import ProviderError, providers_from_env
from .report import write_report
from .research import (
    DeepResearchAgent,
    ResearchBudgetExceeded,
    budget_from_env,
    concurrency_from_env,
)
from .storage import TaskStateStore

app = FastAPI(title="Evidence Research Agent", version="0.3.0")


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1)
    industry: str | None = None
    region: str | None = None
    time_range: str | None = None
    companies: list[str] = Field(default_factory=list)
    breadth: int = Field(default=3, ge=1, le=10)
    depth: int = Field(default=2, ge=1, le=5)


def _request_payload(request: ResearchRequest) -> dict[str, object]:
    return request.model_dump(mode="json")


def _cache_key(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _task_store() -> TaskStateStore:
    store = getattr(app.state, "task_store", None)
    if store is None:
        store = TaskStateStore(os.environ.get("RESEARCH_DB_PATH", "data/research.db"))
        app.state.task_store = store
    return store


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def _execute(request: ResearchRequest) -> dict[str, object]:
    search, model = providers_from_env()
    agent = DeepResearchAgent(
        search=search,
        model=model,
        concurrency=concurrency_from_env(),
        budget=budget_from_env(),
    )
    prompt = build_industry_prompt(
        IndustryRequest(
            question=request.query,
            industry=request.industry,
            region=request.region,
            time_range=request.time_range,
            companies=request.companies,
        )
    )
    result = await agent.research(query=prompt, breadth=request.breadth, depth=request.depth)
    report = await write_report(
        prompt=prompt,
        learnings=result.learnings,
        claims=result.claims,
        evidence=result.evidence,
        sources=result.sources,
        model=agent.model,
    )
    return {
        "report": report,
        **asdict(result),
        "evaluation": evaluate_result(report=report, result=result),
        "budget": agent.budget.snapshot(),
    }


def _http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, ResearchBudgetExceeded):
        return HTTPException(
            status_code=429,
            detail={
                "error": "research_budget_exceeded",
                "resource": exc.resource,
                "limit": exc.limit,
                "used": exc.used,
            },
        )
    if isinstance(exc, ProviderError):
        status_code = {
            "timeout": 504,
            "rate_limit": 429,
            "unavailable": 503,
            "invalid_payload": 502,
            "bad_response": 502,
        }.get(exc.kind, 502)
        return HTTPException(
            status_code=status_code,
            detail={"error": "provider_error", "provider": exc.provider, "kind": exc.kind},
        )
    return HTTPException(status_code=500, detail=str(exc))


async def _run_job(task_id: str, payload: dict[str, object]) -> None:
    store = _task_store()
    store.mark_running(task_id)
    try:
        result = await _execute(ResearchRequest.model_validate(payload))
    except Exception as exc:
        store.mark_failed(task_id, str(exc))
        return
    store.mark_completed(task_id, result)


@app.post("/api/research")
async def research(request: ResearchRequest) -> dict[str, object]:
    store = _task_store()
    payload = _request_payload(request)
    cache_key = _cache_key(payload)
    cached = store.find_cached(cache_key)
    if cached is not None and cached.result is not None:
        return {"task_id": cached.id, "cache_hit": True, **cached.result}

    job = store.create(request=payload, cache_key=cache_key)
    store.mark_running(job.id)
    try:
        result = await _execute(request)
    except Exception as exc:
        store.mark_failed(job.id, str(exc))
        raise _http_exception(exc) from exc
    store.mark_completed(job.id, result)
    return {"task_id": job.id, "cache_hit": False, **result}


@app.post("/api/research/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_research_job(
    request: ResearchRequest, background_tasks: BackgroundTasks
) -> dict[str, object]:
    store = _task_store()
    payload = _request_payload(request)
    cache_key = _cache_key(payload)

    cached = store.find_cached(cache_key)
    if cached is not None:
        return {"task_id": cached.id, "status": cached.status, "cache_hit": True}

    active = store.find_active(cache_key)
    if active is not None:
        return {"task_id": active.id, "status": active.status, "cache_hit": False}

    job = store.create(request=payload, cache_key=cache_key)
    background_tasks.add_task(_run_job, job.id, payload)
    return {"task_id": job.id, "status": job.status, "cache_hit": False}


@app.get("/api/research/jobs")
async def list_research_jobs(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, list[dict[str, object]]]:
    return {"jobs": [job.as_dict() for job in _task_store().list(limit=limit)]}


@app.get("/api/research/jobs/{task_id}")
async def get_research_job(task_id: str) -> dict[str, object]:
    job = _task_store().get(task_id)
    if job is None:
        raise HTTPException(status_code=404, detail="research task not found")
    return job.as_dict()
