# Evidence Research Agent

An evidence-first industry research agent built on top of the open-source
[deep-research](https://github.com/dzhng/deep-research) project.

The upstream project turns search results into `learnings` and appends a flat
list of URLs. This version adds a verifiable evidence graph:

```text
research question → claim → evidence quote → source quality → citation audit
```

The goal is not to make the model sound more confident. The goal is to make
each important conclusion traceable, freshness-aware, and explicit about
contradictory or insufficient evidence.

## Highlights

- Extracts claims and exact evidence quotes from crawled pages.
- Preserves source metadata instead of reducing pages to plain strings.
- Canonicalizes URLs and removes common tracking parameters.
- Scores source authority, primaryness, freshness, and specificity.
- Verifies claims as `verified`, `partially_verified`, `contradicted`, or
  `unverified`.
- Generates inline claim citations and a citation coverage audit.
- Accepts industry, region, time range, and company constraints through the API.
- Keeps the original recursive breadth/depth research loop.

## Quick start

Requirements: Node.js 22 and API keys for Firecrawl and an OpenAI-compatible
model endpoint.

```bash
npm install
cp .env.example .env.local
# edit .env.local
npm test
npm start
```

The CLI asks for a research question, breadth, depth, and report mode. The
report is written to `report.md` and includes source quality and citation audit
sections.

## API example

Start the API server:

```bash
npm run api
```

Generate an industry report:

```bash
curl -X POST http://localhost:3051/api/generate-report \
  -H 'content-type: application/json' \
  -d '{
    "query": "What are the major competitive and technology trends?",
    "industry": "新能源汽车",
    "region": "中国",
    "timeRange": "2023-2025",
    "companies": ["比亚迪", "特斯拉", "理想汽车"],
    "breadth": 3,
    "depth": 2
  }'
```

The API returns Markdown for `/api/generate-report`. `/api/research` returns
the structured claims, evidence, and sources as JSON.

## Project structure

```text
src/
├── deep-research.ts       # Recursive research orchestration
├── sources.ts             # URL normalization, source classification, scoring
├── evidence.ts            # Claim/evidence extraction and verification
├── citations.ts           # Inline citation rendering and audit
├── industry.ts            # Industry research constraints and templates
├── types/research.ts      # Evidence graph domain model
└── api.ts                 # JSON and Markdown HTTP endpoints
```

## Evaluation direction

The project is designed to be evaluated on more than answer quality:

- citation coverage: important claims with citations;
- citation entailment: whether the quote actually supports the claim;
- source quality: authority, primaryness, freshness, and specificity;
- contradiction recall: whether conflicting sources are surfaced;
- freshness violations, latency, and cost per report.

## Attribution and license

This project is a derivative work of `dzhng/deep-research`. It retains the
upstream MIT license and attribution while adding the evidence graph, source
scoring, verification, citation audit, and industry-specific request layer.
