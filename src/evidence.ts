import { generateObject } from 'ai';
import { z } from 'zod';

import { getModel, trimPrompt } from './ai/providers';
import { systemPrompt } from './prompt';
import type { Claim, Evidence, SourceDocument } from './types/research';

const EvidenceDraftSchema = z.object({
  claims: z.array(
    z.object({
      text: z.string(),
      category: z.string(),
      importance: z.enum(['high', 'medium', 'low']),
      evidence: z.array(
        z.object({
          sourceId: z.string(),
          quote: z.string(),
          locator: z.string().optional(),
          stance: z.enum(['supports', 'contradicts', 'context']),
          relevanceScore: z.number().min(0).max(1),
        }),
      ),
    }),
  ),
});

const VerificationSchema = z.object({
  verifications: z.array(
    z.object({
      claimId: z.string(),
      verdict: z.enum([
        'verified',
        'partially_verified',
        'contradicted',
        'unverified',
      ]),
      confidence: z.number().min(0).max(1),
      rationale: z.string(),
    }),
  ),
});

function shortId(value: string) {
  return Buffer.from(value).toString('base64url').slice(0, 14).toLowerCase();
}

export async function extractEvidence({
  query,
  sources,
  maxClaims = 8,
}: {
  query: string;
  sources: SourceDocument[];
  maxClaims?: number;
}): Promise<{ claims: Claim[]; evidence: Evidence[] }> {
  if (sources.length === 0) return { claims: [], evidence: [] };

  const sourceText = sources
    .map(
      source =>
        `<source id="${source.id}" url="${source.canonicalUrl}" title="${source.title ?? ''}">\n${trimPrompt(source.content, 12_000)}\n</source>`,
    )
    .join('\n');
  const result = await generateObject({
    model: getModel(),
    abortSignal: AbortSignal.timeout(60_000),
    system: `${systemPrompt()}\nYou are an evidence extraction component. Never invent a quote. Every quote must be copied from one of the supplied sources.`,
    prompt: trimPrompt(
      `Research question: <query>${query}</query>\nExtract at most ${maxClaims} important, independently checkable claims. For every claim, attach exact supporting, contradicting, or contextual quotes from the supplied sources. Use only the source IDs provided below. If a source does not contain evidence, do not cite it.\n\n${sourceText}`,
    ),
    schema: EvidenceDraftSchema,
  });

  const sourceIds = new Set(sources.map(source => source.id));
  const evidence: Evidence[] = [];
  const claims: Claim[] = [];

  for (const draft of result.object.claims) {
    const validEvidence = draft.evidence.filter(
      item => sourceIds.has(item.sourceId) && item.quote.trim(),
    );
    const claimId = `claim-${shortId(draft.text)}`;
    const evidenceIds = validEvidence.map(item => {
      const id = `evidence-${shortId(`${item.sourceId}:${item.quote}`)}`;
      evidence.push({ id, ...item });
      return id;
    });
    claims.push({
      id: claimId,
      text: draft.text,
      category: draft.category,
      importance: draft.importance,
      evidenceIds,
      status: 'unverified',
      confidence: 0,
    });
  }

  return { claims, evidence };
}

export async function verifyClaims({
  claims,
  evidence,
  sources,
}: {
  claims: Claim[];
  evidence: Evidence[];
  sources: SourceDocument[];
}): Promise<Claim[]> {
  if (claims.length === 0) return [];

  const sourceById = new Map(sources.map(source => [source.id, source]));
  const evidenceById = new Map(evidence.map(item => [item.id, item]));
  const verificationInput = claims
    .map(claim => {
      const items = claim.evidenceIds
        .map(id => evidenceById.get(id))
        .filter((item): item is Evidence => Boolean(item))
        .map(item => {
          const source = sourceById.get(item.sourceId);
          return `[${item.id}] ${item.stance} (source score ${source?.quality.score ?? 0}/100): ${item.quote}`;
        })
        .join('\n');
      return `<claim id="${claim.id}">${claim.text}\n${items || 'NO EVIDENCE'}</claim>`;
    })
    .join('\n');

  const result = await generateObject({
    model: getModel(),
    abortSignal: AbortSignal.timeout(60_000),
    system: `${systemPrompt()}\nYou verify claims against supplied evidence. Do not reward a claim merely because a source is authoritative; the evidence must actually entail it.`,
    prompt: trimPrompt(
      `Classify every claim as verified, partially_verified, contradicted, or unverified. A claim with no evidence is unverified. A claim with both supporting and contradicting evidence must not be marked verified. Return one result per claim.\n\n${verificationInput}`,
    ),
    schema: VerificationSchema,
  });

  const verificationById = new Map(
    result.object.verifications.map(item => [item.claimId, item]),
  );
  return claims.map(claim => {
    const verification = verificationById.get(claim.id);
    if (!verification) return claim;
    return {
      ...claim,
      status: verification.verdict,
      confidence: verification.confidence,
      rationale: verification.rationale,
    };
  });
}
