import { useCallback, useRef } from "react";

/**
 * One `Idempotency-Key` per submit (spec 043, Requisito 5.3): the same key
 * while the person retries **the same** thing — a lost answer must not create
 * a second booking — and a new one as soon as what they send changes or it
 * went through.
 */
export type KeySlot = { signature: string; key: string } | null;

export function keyFor(slot: KeySlot, signature: string, fresh: () => string): { signature: string; key: string } {
  return slot && slot.signature === signature ? slot : { signature, key: fresh() };
}

function uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // Old browsers: RFC 4122 v4 from getRandomValues.
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export function useIdempotencyKey() {
  const slot = useRef<KeySlot>(null);
  const take = useCallback((payload: unknown) => {
    slot.current = keyFor(slot.current, JSON.stringify(payload), uuid);
    return slot.current.key;
  }, []);
  const done = useCallback(() => {
    slot.current = null;
  }, []);
  return { take, done };
}
