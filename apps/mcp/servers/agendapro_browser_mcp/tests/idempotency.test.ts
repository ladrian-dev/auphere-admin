import { describe, expect, it } from 'vitest';

import { composeIdempotencyKey } from '../src/idempotency.js';

describe('composeIdempotencyKey', () => {
  it('produces auphere_<tenant>_<intent_hash>', () => {
    const key = composeIdempotencyKey({
      tenantId: '11111111-2222-3333-4444-555555555555',
      intentHash: 'abc123XYZ',
    });
    expect(key).toBe('auphere_11111111-2222-3333-4444-555555555555_abc123XYZ');
  });

  it('rejects malformed tenant_id', () => {
    expect(() =>
      composeIdempotencyKey({ tenantId: 'not-a-uuid!', intentHash: 'abc' }),
    ).toThrow(/tenant_id format/);
  });

  it('rejects intent_hash with disallowed characters', () => {
    expect(() =>
      composeIdempotencyKey({
        tenantId: '11111111-2222-3333-4444-555555555555',
        intentHash: 'has spaces',
      }),
    ).toThrow(/intent_hash format/);
  });
});
