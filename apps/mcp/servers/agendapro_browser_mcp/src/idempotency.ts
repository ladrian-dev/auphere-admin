/**
 * Idempotency key composition para AgendaPro create_appointment.
 *
 * El server compone la key DENTRO del proceso para que ni el LLM ni el
 * adapter Python puedan forzar key arbitraria — eso protege contra
 * un caller malicioso que intente saltearse la guard de doble-booking.
 *
 * Forma:  ``auphere_<tenant_id>_<intent_hash>``
 *
 * El ``intent_hash`` lo aporta el adapter Python (computado del turn),
 * pero la primera mitad (``auphere_<tenant_id>_``) se garantiza acá.
 */

const PREFIX = 'auphere_';

export function composeIdempotencyKey(opts: {
  tenantId: string;
  intentHash: string;
}): string {
  if (!/^[a-f0-9-]+$/i.test(opts.tenantId)) {
    throw new Error(`unexpected tenant_id format: ${opts.tenantId}`);
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(opts.intentHash)) {
    throw new Error(`unexpected intent_hash format`);
  }
  return `${PREFIX}${opts.tenantId}_${opts.intentHash}`;
}
