from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

from .evidence import extract_evidence, verify_claims
from .models import ResearchResult
from .providers import JsonModel, SearchProvider
from .sources import sources_from_search


class ResearchBudgetExceeded(RuntimeError):
    def __init__(self, *, resource: str, limit: int | float, used: int | float) -> None:
        self.resource = resource
        self.limit = limit
        self.used = used
        super().__init__(f"research budget exceeded for {resource}: {used}/{limit}")


@dataclass
class ResearchBudget:
    max_searches: int = 20
    max_model_calls: int = 40
    max_seconds: float = 180.0
    search_calls: int = 0
    model_calls: int = 0
    _started_at: float = field(default_factory=time.monotonic, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_searches < 1 or self.max_model_calls < 1 or self.max_seconds <= 0:
            raise ValueError("research budget limits must be positive")

    def _check_time(self) -> None:
        elapsed = time.monotonic() - self._started_at
        if elapsed >= self.max_seconds:
            raise ResearchBudgetExceeded(
                resource="seconds",
                limit=self.max_seconds,
                used=round(elapsed, 3),
            )

    def consume_search(self) -> None:
        self._check_time()
        if self.search_calls >= self.max_searches:
            raise ResearchBudgetExceeded(
                resource="search_calls",
                limit=self.max_searches,
                used=self.search_calls,
            )
        self.search_calls += 1

    def consume_model(self) -> None:
        self._check_time()
        if self.model_calls >= self.max_model_calls:
            raise ResearchBudgetExceeded(
                resource="model_calls",
                limit=self.max_model_calls,
                used=self.model_calls,
            )
        self.model_calls += 1

    def snapshot(self) -> dict[str, object]:
        elapsed = round(time.monotonic() - self._started_at, 3)
        return {
            "max_searches": self.max_searches,
            "search_calls": self.search_calls,
            "remaining_searches": max(0, self.max_searches - self.search_calls),
            "max_model_calls": self.max_model_calls,
            "model_calls": self.model_calls,
            "remaining_model_calls": max(0, self.max_model_calls - self.model_calls),
            "max_seconds": self.max_seconds,
            "elapsed_seconds": elapsed,
        }


class _BudgetedJsonModel:
    def __init__(self, model: JsonModel, budget: ResearchBudget) -> None:
        self.model = model
        self.budget = budget

    async def generate_json(self, *, system: str, prompt: str) -> dict[str, Any]:
        self.budget.consume_model()
        return await self.model.generate_json(system=system, prompt=prompt)


async def _gather_cancel_on_error[T](coroutines: list[Coroutine[Any, Any, T]]) -> list[T]:
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float = 0.1) -> float:
    try:
        return max(minimum, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


def concurrency_from_env() -> int:
    return _env_int("FIRECRAWL_CONCURRENCY", 2)


def budget_from_env() -> ResearchBudget:
    return ResearchBudget(
        max_searches=_env_int("RESEARCH_MAX_SEARCHES", 20),
        max_model_calls=_env_int("RESEARCH_MAX_MODEL_CALLS", 40),
        max_seconds=_env_float("RESEARCH_MAX_SECONDS", 180.0),
    )


class DeepResearchAgent:
    def __init__(
        self,
        *,
        search: SearchProvider,
        model: JsonModel,
        concurrency: int = 2,
        budget: ResearchBudget | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self.search = search
        self.budget = budget or ResearchBudget()
        self.model = _BudgetedJsonModel(model, self.budget)
        self.semaphore = asyncio.Semaphore(concurrency)

    async def _generate_queries(self, query: str, breadth: int) -> list[dict[str, str]]:
        payload = await self.model.generate_json(
            system=(
                "You generate diverse, focused search queries for an industry researcher. Return JSON only."
            ),
            prompt=(
                f"Generate at most {breadth} unique SERP queries for this research question: {query}\n"
                "Return {queries: [{query, researchGoal}]} and avoid near-duplicates."
            ),
        )
        queries = []
        raw_queries = payload.get("queries", []) if isinstance(payload, dict) else []
        if not isinstance(raw_queries, list):
            raw_queries = []
        for item in raw_queries:
            if isinstance(item, dict) and isinstance(item.get("query"), str):
                queries.append({"query": item["query"], "researchGoal": str(item.get("researchGoal", ""))})
        return queries[:breadth] or [{"query": query, "researchGoal": query}]

    async def _run_query(self, query: str, goal: str) -> tuple[ResearchResult, list[str]]:
        self.budget.consume_search()
        async with self.semaphore:
            items = await self.search.search(query, limit=5)
        sources = sources_from_search(items)
        claims, evidence = await extract_evidence(query=query, sources=sources, model=self.model)
        learnings = [claim.text for claim in claims]
        follow_up_payload = await self.model.generate_json(
            system="You identify concise follow-up research directions. Return JSON only.",
            prompt=(
                f"Research goal: {goal}\nFindings:\n"
                + "\n".join(learnings)
                + "\nReturn {questions: [string]}."
            ),
        )
        raw_follow_ups = follow_up_payload.get("questions", []) if isinstance(follow_up_payload, dict) else []
        if not isinstance(raw_follow_ups, list):
            raw_follow_ups = []
        follow_ups = [item for item in raw_follow_ups if isinstance(item, str)]
        return (
            ResearchResult(
                learnings=learnings,
                visited_urls=[source.canonical_url for source in sources],
                sources=sources,
                evidence=evidence,
                claims=claims,
            ),
            follow_ups,
        )

    @staticmethod
    def _merge(results: list[ResearchResult]) -> ResearchResult:
        merged = ResearchResult()
        for result in results:
            merged.learnings.extend(result.learnings)
            merged.visited_urls.extend(result.visited_urls)
            merged.sources.extend(result.sources)
            merged.evidence.extend(result.evidence)
            merged.claims.extend(result.claims)
        merged.learnings = list(dict.fromkeys(merged.learnings))
        merged.visited_urls = list(dict.fromkeys(merged.visited_urls))
        merged.sources = list({source.id: source for source in merged.sources}.values())
        merged.evidence = list({item.id: item for item in merged.evidence}.values())
        merged.claims = list({claim.id: claim for claim in merged.claims}.values())
        return merged

    async def research(self, *, query: str, breadth: int = 3, depth: int = 2) -> ResearchResult:
        queries = await self._generate_queries(query, breadth)
        branches = await _gather_cancel_on_error(
            [self._run_query(item["query"], item["researchGoal"]) for item in queries]
        )
        results = [result for result, _ in branches]
        if depth > 1:
            follow_up_queries = [question for _, questions in branches for question in questions]
            child_results = await _gather_cancel_on_error(
                [
                    self.research(query=question, breadth=max(1, breadth // 2), depth=depth - 1)
                    for question in follow_up_queries[: max(1, breadth // 2)]
                ]
            )
            results.extend(child_results)

        merged = self._merge(results)
        merged.claims = await verify_claims(
            claims=merged.claims,
            evidence=merged.evidence,
            sources=merged.sources,
            model=self.model,
        )
        return merged
