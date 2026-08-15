import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { canonicalizeUrl, classifySource } from './sources';

describe('source normalization', () => {
  it('removes tracking parameters and fragments', () => {
    assert.equal(
      canonicalizeUrl(
        'https://example.com/report/?utm_source=newsletter&id=7#section',
      ),
      'https://example.com/report?id=7',
    );
  });

  it('classifies official and research domains', () => {
    assert.equal(classifySource('https://www.gov.cn/report'), 'regulator');
    assert.equal(classifySource('https://arxiv.org/abs/1234'), 'research');
  });
});
