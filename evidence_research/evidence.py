from __future__ import annotations

import hashlib

from .models import Claim, ClaimStatus, Evidence, SourceDocument
from .providers import JsonModel


def _short_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:14]


def _source_context(sources: list[SourceDocument]) -> str:
    return "\n".join(
        f'<source id="{source.id}" url="{source.canonical_url}" title="{source.title or ""}">\n'
        f"{source.content[:12000]}\n</source>"
        for source in sources
    )


async def extract_evidence(
    *, query: str, sources: list[SourceDocument], model: JsonModel, max_claims: int = 8
) -> tuple[list[Claim], list[Evidence]]:
    if not sources:
        return [], []
    payload = await model.generate_json(
        system=(
            "You extract verifiable research claims. Never invent quotes. "
            "Every quote must be copied from the supplied sources. Return JSON only."
        ),
        prompt=(
            f"Research question: {query}\nExtract at most {max_claims} important, checkable claims. "
            "For each claim, include exact supporting, contradicting, or contextual quotes. "
            "Use only the supplied source IDs. Output {claims: [{text, category, importance, "
            "evidence: [{sourceId, quote, locator, stance, relevanceScore}]}]}.\n\n"
            f"{_source_context(sources)}"
        ),
    )

    source_ids = {source.id for source in sources}
    claims: list[Claim] = []
    evidence: list[Evidence] = []
    for raw_claim in payload.get("claims", []):
        if not isinstance(raw_claim, dict) or not isinstance(raw_claim.get("text"), str):
            continue
        claim_id = f"claim-{_short_id(raw_claim['text'])}"
        evidence_ids: list[str] = []
        for raw_item in raw_claim.get("evidence", []):
            if not isinstance(raw_item, dict):
                continue
            source_id = raw_item.get("sourceId")
            quote = raw_item.get("quote")
            if (
                not isinstance(source_id, str)
                or source_id not in source_ids
                or not isinstance(quote, str)
                or not quote.strip()
            ):
                continue
            evidence_id = f"evidence-{_short_id(f'{source_id}:{quote}')}"
            evidence.append(
                Evidence(
                    id=evidence_id,
                    source_id=source_id,
                    quote=quote.strip(),
                    locator=raw_item.get("locator") if isinstance(raw_item.get("locator"), str) else None,
                    stance=str(raw_item.get("stance", "context")),
                    relevance_score=float(raw_item.get("relevanceScore", 0.5)),
                )
            )
            evidence_ids.append(evidence_id)
        claims.append(
            Claim(
                id=claim_id,
                text=raw_claim["text"],
                category=str(raw_claim.get("category", "general")),
                importance=str(raw_claim.get("importance", "medium")),
                evidence_ids=evidence_ids,
            )
        )
    return claims, evidence


async def verify_claims(
    *, claims: list[Claim], evidence: list[Evidence], sources: list[SourceDocument], model: JsonModel
) -> list[Claim]:
    if not claims:
        return []
    source_by_id = {source.id: source for source in sources}
    evidence_by_id = {item.id: item for item in evidence}
    claim_context = []
    for claim in claims:
        items = []
        for evidence_id in claim.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if not item:
                continue
            source = source_by_id.get(item.source_id)
            items.append(
                f"[{item.id}] {item.stance}; "
                f"source score={source.quality.score if source else 0}: {item.quote}"
            )
        claim_context.append(
            f'<claim id="{claim.id}">{claim.text}\n'
            f'{chr(10).join(items) or "NO EVIDENCE"}</claim>'
        )

    payload = await model.generate_json(
        system=(
            "You verify claims against supplied evidence. Authority alone does not prove a claim. "
            "A claim with no evidence is unverified. Return JSON only."
        ),
        prompt=(
            "Classify every claim as verified, partially_verified, contradicted, or unverified. "
            "Return {verifications: [{claimId, verdict, confidence, rationale}]} for every claim.\n\n"
            + "\n".join(claim_context)
        ),
    )
    verification_by_id = {
        item.get("claimId"): item
        for item in payload.get("verifications", [])
        if isinstance(item, dict) and isinstance(item.get("claimId"), str)
    }
    return [
        Claim(
            **{
                **claim.__dict__,
                "status": ClaimStatus(str(item.get("verdict", ClaimStatus.UNVERIFIED))),
                "confidence": float(item.get("confidence", 0)),
                "rationale": str(item.get("rationale", "")),
            }
        )
        if (item := verification_by_id.get(claim.id))
        else claim
        for claim in claims
    ]
