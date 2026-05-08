/**
 * Sanity check de los Zod schemas — validan los inputs típicos que el
 * Python adapter envía. Si esto falla, el round-trip Python → Node está
 * roto y ningún test integration va a funcionar.
 */

import { describe, expect, it } from 'vitest';

import {
  BootstrapSessionInputSchema,
  CreateAppointmentInputSchema,
  HealthCheckInputSchema,
} from '../src/schemas.js';

describe('Zod schemas', () => {
  it('CreateAppointmentInput accepts a typical Python payload', () => {
    const parsed = CreateAppointmentInputSchema.parse({
      context_id: 'ctx-12345',
      intent_hash: 'a'.repeat(40),
      starts_at: '2026-06-01T10:00:00+00:00',
      duration_min: 30,
      service_name: 'Corte',
      barber_external_id: 'ap-barber-1',
      customer_name: 'Juan Pérez',
      customer_phone: '+56911112222',
      customer_email: null,
      notes: null,
    });
    expect(parsed.intent_hash.length).toBe(40);
    expect(parsed.duration_min).toBe(30);
  });

  it('CreateAppointmentInput rejects too-short intent_hash', () => {
    expect(() =>
      CreateAppointmentInputSchema.parse({
        context_id: 'ctx',
        intent_hash: 'short',
        starts_at: '2026-06-01T10:00:00+00:00',
        service_name: 'Corte',
        customer_name: 'X',
        customer_phone: '+5611',
      }),
    ).toThrow();
  });

  it('BootstrapSessionInput rejects empty login', () => {
    expect(() =>
      BootstrapSessionInputSchema.parse({ login: '', password: 'x' }),
    ).toThrow();
  });

  it('HealthCheckInput requires context_id', () => {
    expect(() => HealthCheckInputSchema.parse({})).toThrow();
    const ok = HealthCheckInputSchema.parse({ context_id: 'ctx-12345' });
    expect(ok.context_id).toBe('ctx-12345');
  });
});
