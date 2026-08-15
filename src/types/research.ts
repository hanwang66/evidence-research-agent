export type SourceType =
  | 'official'
  | 'regulator'
  | 'research'
  | 'media'
  | 'company'
  | 'blog'
  | 'unknown';

export type ClaimStatus =
  | 'verified'
  | 'partially_verified'
  | 'contradicted'
  | 'unverified';

export interface SourceQuality {
  authority: number;
  primaryness: number;
  freshness: number;
  specificity: number;
  score: number;
  reasons: string[];
}

export interface SourceDocument {
  id: string;
  url: string;
  canonicalUrl: string;
  title?: string;
  publisher?: string;
  publishedAt?: string;
  fetchedAt: string;
  sourceType: SourceType;
  content: string;
  quality: SourceQuality;
}

export interface Evidence {
  id: string;
  sourceId: string;
  quote: string;
  locator?: string;
  stance: 'supports' | 'contradicts' | 'context';
  relevanceScore: number;
}

export interface Claim {
  id: string;
  text: string;
  category: string;
  importance: 'high' | 'medium' | 'low';
  evidenceIds: string[];
  status: ClaimStatus;
  confidence: number;
  rationale?: string;
}

export interface ResearchResult {
  learnings: string[];
  visitedUrls: string[];
  sources: SourceDocument[];
  evidence: Evidence[];
  claims: Claim[];
}
