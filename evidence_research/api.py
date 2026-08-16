from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
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

app = FastAPI(title="Evidence Research Agent", version="0.2.0")


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1)
    industry: str | None = None
    region: str | None = None
    time_range: str | None = None
    companies: list[str] = Field(default_factory=list)
    breadth: int = Field(default=3, ge=1, le=10)
    depth: int = Field(default=2, ge=1, le=5)


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


@app.post("/api/research")
async def research(request: ResearchRequest) -> dict[str, object]:
    try:
        return await _execute(request)
    except ResearchBudgetExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "research_budget_exceeded",
                "resource": exc.resource,
                "limit": exc.limit,
                "used": exc.used,
            },
        ) from exc
    except ProviderError as exc:
        status_code = {
            "timeout": 504,
            "rate_limit": 429,
            "unavailable": 503,
            "invalid_payload": 502,
            "bad_response": 502,
        }.get(exc.kind, 502)
        raise HTTPException(
            status_code=status_code,
            detail={"error": "provider_error", "provider": exc.provider, "kind": exc.kind},
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
