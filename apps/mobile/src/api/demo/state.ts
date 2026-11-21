import type { components } from "../schema.gen";

import { NOTICE_KINDS, demoCurrency, seeds, type Currency } from "./data";
import { Inbox } from "./inbox";
import { resetReservas } from "./reservas";

type S = components["schemas"];

/**
 * Everything the example API remembers, in memory only (nothing of a demo
 * customer is written to disk, like the real data — `query.ts`). Built on the
 * first request, so its «now» is when the app started asking.
 */
export type DemoState = {
  born: number;
  currency: Currency;
  inbox: Inbox;
  notices: S["NoticesOut"];
  corrections: Map<string, S["CorrectionOut"]>;
  /** A correction's draft by its `Idempotency-Key`: a retry is the same draft. */
  correctionKeys: Map<string, string>;
  /** The contact's names, to find them again when a draft is edited (52.5). */
  correctionNames: Map<string, string[]>;
  /** How many credentials were handed out (each sign-in and renewal is a new one). */
  issued: number;
};

let current: DemoState | null = null;

export function state(): DemoState {
  if (!current) {
    const born = Date.now();
    current = {
      born,
      currency: demoCurrency(),
      inbox: new Inbox(seeds(born), born),
      notices: { kinds: [...NOTICE_KINDS], quiet_outside_hours: true },
      corrections: new Map(),
      correctionKeys: new Map(),
      correctionNames: new Map(),
      issued: 0,
    };
  }
  return current;
}

/** Back to the start: the next request builds the example again (tests, and a reload). */
export function resetState(): void {
  current = null;
  resetReservas();
}
