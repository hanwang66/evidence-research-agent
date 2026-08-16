from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from evidence_research.evaluation import evaluate_result
from evidence_research.industry import IndustryRequest, build_industry_prompt
from evidence_research.providers import providers_from_env
from evidence_research.report import write_report
from evidence_research.research import DeepResearchAgent


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"Evaluation cases must be a JSON array of objects: {path}")
    return payload


async def _run_case(*, case: dict[str, Any], agent: DeepResearchAgent, model: Any) -> dict[str, Any]:
    request = IndustryRequest(
        question=str(case["query"]),
        industry=case.get("industry"),
        region=case.get("region"),
        time_range=case.get("time_range"),
        companies=case.get("companies", []),
    )
    prompt = build_industry_prompt(request)
    result = await agent.research(
        query=prompt,
        breadth=int(case.get("breadth", 2)),
        depth=int(case.get("depth", 1)),
    )
    report = await write_report(
        prompt=prompt,
        learnings=result.learnings,
        claims=result.claims,
        evidence=result.evidence,
        sources=result.sources,
        model=model,
    )
    return {
        "id": str(case.get("id", case["query"])),
        "query": case["query"],
        "evaluation": evaluate_result(report=report, result=result),
    }


async def _run(cases_path: Path) -> dict[str, Any]:
    search, model = providers_from_env()
    agent = DeepResearchAgent(search=search, model=model)
    cases = _load_cases(cases_path)
    results = [await _run_case(case=case, agent=agent, model=model) for case in cases]
    return {
        "case_count": len(results),
        "passed_count": sum(1 for item in results if item["evaluation"]["passed"]),
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic research reliability evaluation")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/cases.json"),
        help="Path to a JSON evaluation case file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the JSON evaluation report; stdout when omitted",
    )
    args = parser.parse_args()
    report = asyncio.run(_run(args.cases))
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0 if report["passed_count"] == report["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
