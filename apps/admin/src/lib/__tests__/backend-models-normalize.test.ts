/**
 * Spec 059: el panel y la API no se despliegan en el mismo instante (Vercel y ECS).
 * Si el panel nuevo lee una API que aún no trae `uses`, `sale` ni `sale_policy`,
 * Modelos tiene que pintarse igual, sin afirmar nada que no sabe: el uso queda «sin
 * verificar» y la venta «sin objetivo».
 */
import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { normalizeList, normalizeRow } from "../backend-models";
import { isInUse, saleChip, usesLines } from "../../app/(dashboard)/models/labels";

const OLD_ROW = {
  uuid: "11111111-1111-4111-8111-111111111111",
  display_name: "Sol",
  deployment: { id: "openai/gpt-5.6-sol", status: "active" },
  current_price: null,
  certified_tasks: [],
  activation_missing: [],
  activation_messages: {},
};

describe("normalizeRow", () => {
  it("fills what an older API does not send, without claiming the model is free", () => {
    const row = normalizeRow(OLD_ROW as never);
    expect(row.uses).toEqual({ defaults: [], agents: 0, clients: [], verified: false, problem: "api_outdated" });
    // Sin datos de la API no se ofrece ni Retirar ni «No disponible»: esa API no protege.
    expect(isInUse(row.uses)).toBe(true);
    expect(usesLines(row.uses).defaults).toMatch(/API/);
    expect(row.sale).toEqual({ state: "unknown", lanes: null, proposed: null });
    expect(row.retirement_blocked_agents).toBeNull();
  });

  it("keeps what the API sends", () => {
    const uses = { defaults: ["respond"], agents: 3, clients: ["A"], verified: true, problem: null };
    const row = normalizeRow({ ...OLD_ROW, uses } as never);
    expect(row.uses).toBe(uses);
  });
});

describe("normalizeList", () => {
  it("fills the policy without a target", () => {
    const list = normalizeList({ items: [OLD_ROW], statuses: ["active"] } as never);
    expect(list.sale_policy).toEqual({ multiplier: null, floor: "1.5", sell_usd_per_million: "10" });
    expect(list.items[0]?.sale.state).toBe("unknown");
  });
});

describe("saleChip", () => {
  it("says nothing when the target is unknown", () => {
    expect(saleChip({ state: "unknown", lanes: null, proposed: null }, false)).toBeNull();
    expect(saleChip({ state: "unknown", lanes: null, proposed: null }, true)).toBeNull();
  });
});
