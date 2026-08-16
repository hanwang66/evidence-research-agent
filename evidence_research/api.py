from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .evaluation import evaluate_result
from .industry import IndustryRequest, build_industry_prompt
from .providers import providers_from_env
from .report import write_report
from .research import DeepResearchAgent

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
    agent = DeepResearchAgent(search=search, model=model)
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
        model=model,
    )
    return {
        "report": report,
        **asdict(result),
        "evaluation": evaluate_result(report=report, result=result),
    }


@app.post("/api/research")
async def research(request: ResearchRequest) -> dict[str, object]:
    try:
        return await _execute(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
