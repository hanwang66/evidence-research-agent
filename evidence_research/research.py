from __future__ import annotations

import asyncio

from .evidence import extract_evidence, verify_claims
from .models import ResearchResult
from .providers import JsonModel, SearchProvider
from .sources import sources_from_search


class DeepResearchAgent:
    def __init__(self, *, search: SearchProvider, model: JsonModel, concurrency: int = 2) -> None:
        self.search = search
        self.model = model
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
        for item in payload.get("queries", []):
            if isinstance(item, dict) and isinstance(item.get("query"), str):
                queries.append({"query": item["query"], "researchGoal": str(item.get("researchGoal", ""))})
        return queries[:breadth] or [{"query": query, "researchGoal": query}]

    async def _run_query(self, query: str, goal: str) -> tuple[ResearchResult, list[str]]:
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
        follow_ups = [item for item in follow_up_payload.get("questions", []) if isinstance(item, str)]
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
        branches = await asyncio.gather(
            *(self._run_query(item["query"], item["researchGoal"]) for item in queries)
        )
        results = [result for result, _ in branches]
        if depth > 1:
            follow_up_queries = [question for _, questions in branches for question in questions]
            child_results = await asyncio.gather(
                *(
                    self.research(query=question, breadth=max(1, breadth // 2), depth=depth - 1)
                    for question in follow_up_queries[: max(1, breadth // 2)]
                )
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
