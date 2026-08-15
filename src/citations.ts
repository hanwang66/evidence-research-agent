import type { Claim, Evidence, SourceDocument } from './types/research';

export function citationId(claim: Claim) {
  return claim.id.replace(/^claim-/, 'C').slice(0, 16);
}

export function renderCitationInstructions({
  claims,
  evidence,
  sources,
}: {
  claims: Claim[];
  evidence: Evidence[];
  sources: SourceDocument[];
}) {
  const evidenceById = new Map(evidence.map(item => [item.id, item]));
  const sourceById = new Map(sources.map(source => [source.id, source]));
  return claims
    .map(claim => {
      const citations = claim.evidenceIds
        .map(id => evidenceById.get(id))
        .filter((item): item is Evidence => Boolean(item))
        .map(item => {
          const source = sourceById.get(item.sourceId);
          return `[${citationId(claim)}] ${item.stance}; ${source?.canonicalUrl ?? item.sourceId}; quote: ${item.quote}`;
        })
        .join('\n');
      return `<claim id="${claim.id}" status="${claim.status}" confidence="${claim.confidence}">${claim.text}\n${citations || 'NO CITATIONS'}</claim>`;
    })
    .join('\n');
}

export function auditCitations(report: string, claims: Claim[]) {
  const importantClaims = claims.filter(claim => claim.importance !== 'low');
  const missing = importantClaims.filter(
    claim => !report.includes(`[${citationId(claim)}]`),
  );
  return {
    passed: missing.length === 0,
    coverage:
      importantClaims.length === 0
        ? 1
        : 1 - missing.length / importantClaims.length,
    missingClaimIds: missing.map(claim => claim.id),
  };
}
