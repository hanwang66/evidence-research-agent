import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { auditCitations, citationId } from './citations';
import type { Claim } from './types/research';

const claim: Claim = {
  id: 'claim-market-growth',
  text: 'The market grew year over year.',
  category: 'growth',
  importance: 'high',
  evidenceIds: ['evidence-1'],
  status: 'verified',
  confidence: 0.9,
};

describe('citation audit', () => {
  it('requires citations for important claims', () => {
    assert.equal(citationId(claim), 'Cmarket-growth');
    assert.deepEqual(
      auditCitations('The market grew. [Cmarket-growth]', [claim]),
      {
        passed: true,
        coverage: 1,
        missingClaimIds: [],
      },
    );
  });

  it('reports missing citations', () => {
    const audit = auditCitations('The market grew.', [claim]);
    assert.equal(audit.passed, false);
    assert.equal(audit.coverage, 0);
    assert.deepEqual(audit.missingClaimIds, [claim.id]);
  });
});
