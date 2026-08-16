from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceType(StrEnum):
    OFFICIAL = "official"
    REGULATOR = "regulator"
    RESEARCH = "research"
    MEDIA = "media"
    COMPANY = "company"
    BLOG = "blog"
    UNKNOWN = "unknown"


class ClaimStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class SourceQuality:
    authority: float
    primaryness: float
    freshness: float
    specificity: float
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceDocument:
    id: str
    url: str
    canonical_url: str
    content: str
    source_type: SourceType
    fetched_at: str
    title: str | None = None
    publisher: str | None = None
    published_at: str | None = None
    quality: SourceQuality = field(default_factory=lambda: SourceQuality(0, 0, 0, 0, 0))


@dataclass(frozen=True)
class Evidence:
    id: str
    source_id: str
    quote: str
    stance: str
    relevance_score: float
    locator: str | None = None


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    category: str
    importance: str
    evidence_ids: list[str]
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    confidence: float = 0.0
    rationale: str | None = None


@dataclass
class ResearchResult:
    learnings: list[str] = field(default_factory=list)
    visited_urls: list[str] = field(default_factory=list)
    sources: list[SourceDocument] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
