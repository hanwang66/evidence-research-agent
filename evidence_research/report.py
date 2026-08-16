from __future__ import annotations

from .citations import audit_citations, evidence_graph_text
from .models import Claim, Evidence, SourceDocument
from .providers import JsonModel


async def write_report(
    *,
    prompt: str,
    learnings: list[str],
    claims: list[Claim],
    evidence: list[Evidence],
    sources: list[SourceDocument],
    model: JsonModel,
) -> str:
    payload = await model.generate_json(
        system=(
            "You write evidence-grounded Markdown reports. Every important factual claim must cite "
            "one or more supplied claim IDs in the form [C...]. Do not invent citations. "
            "Clearly label contradicted and unverified claims. Return JSON only."
        ),
        prompt=(
            f"Research question:\n{prompt}\n\nLearnings:\n"
            + "\n".join(learnings)
            + "\n\nEvidence graph:\n"
            + evidence_graph_text(claims=claims, evidence=evidence, sources=sources)
            + "\n\nReturn {reportMarkdown: string}."
        ),
    )
    report = str(payload.get("reportMarkdown", ""))
    audit = audit_citations(report, claims)
    source_lines = [
        f"- [{source.id}] {source.title or source.canonical_url} — "
        f"quality {source.quality.score}/100 — {source.canonical_url}"
        for source in sources
    ]
    source_text = "\n".join(source_lines)
    missing = ", ".join(audit["missing_claim_ids"]) or "none"
    return (
        f"{report}\n\n## Sources\n\n{source_text}"
        f"\n\n## Citation audit\n\n- Coverage: {float(audit['coverage']) * 100:.0f}%"
        f"\n- Status: {'passed' if audit['passed'] else 'needs review'}"
        f"\n- Missing claim citations: {missing}\n"
    )
