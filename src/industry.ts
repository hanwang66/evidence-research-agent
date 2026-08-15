export interface IndustryResearchRequest {
  question: string;
  industry?: string;
  region?: string;
  timeRange?: string;
  companies?: string[];
}

const DEFAULT_DIMENSIONS = [
  'market size and growth',
  'competitive landscape',
  'technology and product trends',
  'regulation and policy',
  'key risks and uncertainties',
];

export function buildIndustryPrompt(request: IndustryResearchRequest) {
  const constraints = [
    request.industry && `Industry: ${request.industry}`,
    request.region && `Region: ${request.region}`,
    request.timeRange && `Time range: ${request.timeRange}`,
    request.companies?.length && `Companies: ${request.companies.join(', ')}`,
  ].filter(Boolean);

  return [
    request.question,
    constraints.length
      ? `Research constraints:\n${constraints.join('\n')}`
      : '',
    `Unless the question clearly excludes them, cover:\n${DEFAULT_DIMENSIONS.map(item => `- ${item}`).join('\n')}`,
    'Prefer primary, regulator, official, academic, and reputable media sources. Preserve conflicting evidence.',
  ]
    .filter(Boolean)
    .join('\n\n');
}
