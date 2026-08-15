# Evidence Research Agent

Evidence-first industry research agent. This branch is the Python rewrite of
the original TypeScript implementation and is built on top of the open-source
[dzhng/deep-research](https://github.com/dzhng/deep-research) project.

The project turns a research question into a traceable evidence graph:

```text
question → research plan → search → source quality → claim → evidence quote → verification → cited report
```

The design goal is not simply to generate a fluent answer. Every important
conclusion should be traceable to an exact quote, a source URL, a quality score,
and a verification status.

## Feature map

| Capability | What it does | Python status |
|---|---|---|
| Recursive research | Expands a question through breadth/depth controlled searches | Implemented |
| Industry constraints | Adds industry, region, time range, and company context | Implemented |
| Source normalization | Canonicalizes URLs and removes tracking parameters | Implemented |
| Source classification | Identifies regulator, official, research, media, and unknown sources | Implemented |
| Source quality scoring | Scores authority, primaryness, freshness, and specificity | Implemented |
| Evidence extraction | Extracts exact quotes and maps them to source IDs | Implemented |
| Claim verification | Marks claims as verified, partially verified, contradicted, or unverified | Implemented |
| Citation audit | Measures citation coverage and reports missing citations | Implemented |
| Async concurrency | Limits concurrent search requests with `asyncio.Semaphore` | Implemented |
| FastAPI endpoint | Runs a complete research request and returns Markdown plus evidence data | Implemented |
| Persistent research jobs | Resume, cache, and inspect historical tasks | Planned |
| Evaluation dashboard | Track entailment, source quality, freshness, cost, and latency | Planned |

## Why this is different from a basic Deep Research demo

The upstream implementation reduces crawled pages to `learnings` and a flat URL
list. This version keeps the relationship between:

```text
Claim → Evidence → Source
```

That enables three reliability checks:

1. Does the quoted passage actually support the claim?
2. Is the source authoritative, primary, and fresh enough for the question?
3. Are there independent sources that contradict the conclusion?

An authoritative source is not automatically proof of a claim. Contradictions
and insufficient evidence are preserved in the report instead of being hidden.

## TypeScript → Python mapping

| Original TypeScript module | Python module | Responsibility |
|---|---|---|
| `src/deep-research.ts` | `evidence_research/research.py` | Research orchestration and recursion |
| `src/sources.ts` | `evidence_research/sources.py` | URL normalization and source scoring |
| `src/evidence.ts` | `evidence_research/evidence.py` | Evidence extraction and claim verification |
| `src/citations.ts` | `evidence_research/citations.py` | Citation rendering and audit |
| `src/industry.ts` | `evidence_research/industry.py` | Industry-specific constraints |
| `src/api.ts` | `evidence_research/api.py` | FastAPI HTTP API |
| Zod schemas | Dataclasses and typed model boundaries | Structured domain data |
| `p-limit` | `asyncio.Semaphore` | Bounded concurrency |

The original TypeScript version remains on `main` as the `v0.1.0` baseline. The
Python migration is developed on `rewrite/python` so the rewrite can be
reviewed as a focused architectural change.

## Quick start

Requirements: Python 3.12, `uv`, a Firecrawl API key, and an OpenAI-compatible
model API key.

```bash
uv sync --extra dev
cp .env.example .env.local
# edit .env.local

uv run pytest
uv run uvicorn evidence_research.api:app --reload --port 3051
```

The API exposes `GET /healthz` and `POST /api/research`.

```bash
curl -X POST http://localhost:3051/api/research \
  -H 'content-type: application/json' \
  -d '{
    "query": "What are the major competitive and technology trends?",
    "industry": "新能源汽车",
    "region": "中国",
    "time_range": "2023-2025",
    "companies": ["比亚迪", "特斯拉", "理想汽车"],
    "breadth": 3,
    "depth": 2
  }'
```

The response contains:

- `report`: Markdown report with inline claim citations;
- `claims`: verification status and confidence for each conclusion;
- `evidence`: exact quotes mapped to source IDs;
- `sources`: URLs and quality scores;
- `learnings` and `visited_urls`: compatibility fields from the upstream flow.

## Project structure

```text
evidence_research/
├── api.py          # FastAPI interface
├── models.py       # Research domain models
├── research.py     # Recursive orchestration
├── providers.py    # Firecrawl and OpenAI-compatible adapters
├── sources.py      # URL normalization and source quality scoring
├── evidence.py     # Claim/evidence extraction and verification
├── citations.py    # Citation rendering and audit
├── industry.py     # Industry research request handling
└── report.py       # Evidence-grounded report generation
```

## Evaluation plan

The next evaluation layer will measure more than answer fluency:

- citation coverage: important claims with citations;
- citation entailment: whether the quote actually supports the claim;
- source quality: authority, primaryness, freshness, and specificity;
- contradiction recall: whether conflicting sources are surfaced;
- freshness violations, latency, and cost per report.

## Development workflow

```bash
git switch rewrite/python
uv run pytest
uv run ruff check evidence_research tests
uv run mypy evidence_research
```

The pull request for this branch documents the migration from TypeScript to
Python while keeping the original `main` branch stable.

## Attribution and license

This is a derivative work of `dzhng/deep-research`. The upstream MIT license
and attribution are retained. The Python evidence graph, source scoring,
verification, citation audit, industry request layer, and FastAPI integration
are the additions in this branch.
