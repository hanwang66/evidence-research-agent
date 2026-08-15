import { createHash } from 'node:crypto';
import type { SearchResponse } from '@mendable/firecrawl-js';

import type {
  SourceDocument,
  SourceQuality,
  SourceType,
} from './types/research';

type SearchItem = {
  url?: string;
  markdown?: string;
  title?: string;
  description?: string;
  metadata?: {
    title?: string;
    description?: string;
    publishedTime?: string;
    publishedAt?: string;
    sourceURL?: string;
  };
};

const TRACKING_PARAMS = new Set([
  'fbclid',
  'gclid',
  'mc_cid',
  'mc_eid',
  'ref',
  'utm_campaign',
  'utm_content',
  'utm_medium',
  'utm_source',
  'utm_term',
]);

const OFFICIAL_DOMAINS = [
  'gov',
  'gov.cn',
  'gov.uk',
  'europa.eu',
  'sec.gov',
  'who.int',
  'worldbank.org',
  'stats.gov.cn',
  'caam.org.cn',
];

const RESEARCH_DOMAINS = [
  'arxiv.org',
  'doi.org',
  'nature.com',
  'sciencedirect.com',
];

const MEDIA_DOMAINS = [
  'reuters.com',
  'ft.com',
  'bloomberg.com',
  'nytimes.com',
  'wsj.com',
  'theguardian.com',
];

function shortHash(value: string) {
  return createHash('sha256').update(value).digest('hex').slice(0, 12);
}

export function canonicalizeUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    url.hash = '';
    for (const key of [...url.searchParams.keys()]) {
      if (TRACKING_PARAMS.has(key.toLowerCase())) {
        url.searchParams.delete(key);
      }
    }
    url.pathname = url.pathname.replace(/\/+$/, '') || '/';
    return url.toString();
  } catch {
    return rawUrl.trim();
  }
}

function matchesDomain(hostname: string, domain: string) {
  return hostname === domain || hostname.endsWith(`.${domain}`);
}

export function classifySource(url: string): SourceType {
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    if (OFFICIAL_DOMAINS.some(domain => matchesDomain(hostname, domain))) {
      return hostname.includes('gov') || hostname.includes('sec.gov')
        ? 'regulator'
        : 'official';
    }
    if (RESEARCH_DOMAINS.some(domain => matchesDomain(hostname, domain))) {
      return 'research';
    }
    if (MEDIA_DOMAINS.some(domain => matchesDomain(hostname, domain))) {
      return 'media';
    }
    if (hostname.endsWith('.edu') || hostname.endsWith('.edu.cn')) {
      return 'research';
    }
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

function scoreSource({
  url,
  title,
  content,
  publishedAt,
  sourceType,
  maxAgeDays = 730,
}: {
  url: string;
  title?: string;
  content: string;
  publishedAt?: string;
  sourceType: SourceType;
  maxAgeDays?: number;
}): SourceQuality {
  const reasons: string[] = [];
  const authority =
    sourceType === 'regulator'
      ? 1
      : sourceType === 'official' || sourceType === 'research'
        ? 0.85
        : sourceType === 'media'
          ? 0.7
          : 0.4;
  const primaryness =
    sourceType === 'regulator' || sourceType === 'official'
      ? 1
      : sourceType === 'research'
        ? 0.85
        : 0.55;
  const specificity = Math.min(
    1,
    (content.length / 3000) * 0.6 + (title ? 0.4 : 0),
  );

  let freshness = 0.35;
  if (publishedAt) {
    const published = Date.parse(publishedAt);
    if (!Number.isNaN(published)) {
      const ageDays = Math.max(0, (Date.now() - published) / 86_400_000);
      freshness = Math.max(0, 1 - ageDays / maxAgeDays);
      reasons.push(`published ${Math.round(ageDays)} days ago`);
    }
  } else {
    reasons.push('publication date unavailable');
  }

  if (authority >= 0.85) reasons.push(`source type: ${sourceType}`);
  if (specificity >= 0.7) reasons.push('contains substantial source content');
  const score = Math.round(
    (authority * 0.3 +
      primaryness * 0.25 +
      freshness * 0.2 +
      specificity * 0.25) *
      100,
  );

  return { authority, primaryness, freshness, specificity, score, reasons };
}

export function sourcesFromSearchResponse(
  result: SearchResponse,
  maxAgeDays?: number,
): SourceDocument[] {
  const fetchedAt = new Date().toISOString();
  const sources = new Map<string, SourceDocument>();

  for (const rawItem of result.data as SearchItem[]) {
    if (!rawItem.url || !rawItem.markdown?.trim()) continue;
    const canonicalUrl = canonicalizeUrl(rawItem.url);
    const sourceType = classifySource(canonicalUrl);
    const title = rawItem.title ?? rawItem.metadata?.title;
    const publishedAt =
      rawItem.metadata?.publishedAt ?? rawItem.metadata?.publishedTime;
    const source: SourceDocument = {
      id: `src-${shortHash(canonicalUrl)}`,
      url: rawItem.url,
      canonicalUrl,
      title,
      publisher: rawItem.metadata?.sourceURL,
      publishedAt,
      fetchedAt,
      sourceType,
      content: rawItem.markdown.trim(),
      quality: scoreSource({
        url: canonicalUrl,
        title,
        content: rawItem.markdown,
        publishedAt,
        sourceType,
        maxAgeDays,
      }),
    };
    sources.set(canonicalUrl, source);
  }

  return [...sources.values()];
}
