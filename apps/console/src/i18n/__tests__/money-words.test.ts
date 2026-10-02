import { describe, expect, it } from "vitest";

import { messages } from "../messages";

/**
 * Spec 027 (CE-001): the partner reads money. No copy about the balance,
 * caps or spend may name the internal unit — «créditos», «cupo», «unidades
 * de consumo», «tokens». The ledger keeps credits; the screen does not.
 */
const MONEY_KEYS = [
  /^hu\.usage\.wallet/,
  /^hu\.usage\.allocations/,
  /^hu\.home\.(kpi\.credit|credit|spend|attention\.wallet|issue\.(out_of_quota|wallet_empty)|fix\.(out_of_quota|wallet_empty))/,
  /^sum\.credit/,
  /^clients\.quota\./,
  /^clients\.setup\.(quota|next\.quota|why\.quota)$/,
  /^clients\.col\.credit/,
  /^clients\.health\.(outOfQuota|fix\.quota)$/,
  /^clients\.detail\.missing\.quota$/,
  /^membership\.credit\./,
  /^membership\.cancel\.done$/,
  /^notif\.kind\.client\.(out_of_quota|activated\.cannot_serve)/,
  /^wizard\.review\.pending\.credit/,
];

const UNIT_WORDS = /\bcr[eé]ditos?\b|\bcupos?\b|unidades de consumo|\btokens?\b|\bcredits?\b|\bquota\b|consumption units/i;

describe("el partner ve dinero (spec 027, CE-001)", () => {
  const keys = Object.keys(messages).filter((k) => MONEY_KEYS.some((re) => re.test(k)));

  it("the sweep finds the money copy (if this drops, the patterns broke)", () => {
    expect(keys.length).toBeGreaterThan(40);
  });

  it("no money copy names the internal unit", () => {
    const offenders = keys.flatMap((k) =>
      (["es", "en"] as const)
        .filter((l) => UNIT_WORDS.test(String((messages as Record<string, Record<string, string>>)[k]![l])))
        .map((l) => `${k} (${l}): ${(messages as Record<string, Record<string, string>>)[k]![l]}`),
    );
    expect(offenders, offenders.join("\n")).toEqual([]);
  });
});
