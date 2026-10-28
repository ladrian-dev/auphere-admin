import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RouterAnomalies } from "@/lib/backend-models";
import type { LedgerDiff, MetaDiff } from "@/lib/backend-levers";

import { anomalyTotals, daysLabel, ledgerExplain, metaExplain, parseDays, sinceFor } from "../anomalies";
import { LedgerDiffs, MetaDiffs } from "../reconciliations-view";

const P1 = "pppppppp-0000-0000-0000-000000000001";
const T1 = "11111111-0000-0000-0000-000000000001";
const CH = "cccccccc-0000-0000-0000-000000000001";

const BAG: LedgerDiff = {
  kind: "bag",
  partner_id: P1,
  partner_name: "Demo Auditoría",
  currency: "EUR",
  tenant_id: T1,
  tenant_name: "Volumen 03",
  balance: 5_000_000,
  entries: 4_990_000,
  last_entry: 5_000_000,
};
const ACCOUNT: LedgerDiff = {
  kind: "account",
  partner_id: P1,
  partner_name: "Demo Auditoría",
  currency: "USD",
  ledger: 10_000_000,
  transfers: 9_000_001,
};
const MISSING: MetaDiff = {
  tenant_id: T1,
  tenant_name: "Volumen 03",
  channel_id: CH,
  identifier: "+34600000001",
  date: "2026-10-27",
  meta_count: 120,
  stored_count: 117,
  diff: 3,
};
const EXTRA: MetaDiff = { ...MISSING, identifier: null, date: "2026-10-26", meta_count: 10, stored_count: 11, diff: -1 };

const ROUTER: RouterAnomalies = {
  items: [
    { tenant_id: T1, tenant_name: "Volumen 03", task: "conversation", kind: "reserve_model", decision_id: "d1", created_at: "2026-10-27T10:00:00Z" },
    { tenant_id: T1, tenant_name: "Volumen 03", task: "conversation", kind: "no_model", decision_id: "d2", created_at: "2026-10-27T11:00:00Z" },
  ],
  waiting_no_model: [{ tenant_id: T1, tenant_name: "Volumen 03", conversations: 4 }],
  since: "2026-10-21T00:00:00Z",
};

/** Spec 047 (T172; 54.9, 43.9, 2.6): the anomalies on Estado. */
describe("the anomalies of Estado", () => {
  it("offers a few periods and reads anything else as the last 7 days", () => {
    expect(parseDays(undefined)).toBe(7);
    expect(parseDays("30")).toBe(30);
    expect(parseDays(["1", "90"])).toBe(1);
    expect(parseDays("45")).toBe(7);
    expect(parseDays("abc")).toBe(7);
    expect(sinceFor(7, new Date("2026-10-28T00:00:00Z"))).toBe("2026-10-21T00:00:00.000Z");
    expect(daysLabel(1)).toBe("Último día");
    expect(daysLabel(30)).toBe("Últimos 30 días");
  });

  it("explains each difference of the ledger in words, exact and in its currency", () => {
    expect(ledgerExplain(BAG)).toEqual({
      what: "Bolsa de Volumen 03",
      detail: "Saldo guardado 50,00\u00a0€; la suma de sus asientos da 49,90\u00a0€ y el último asiento dice 50,00\u00a0€.",
    });
    expect(ledgerExplain({ ...BAG, last_entry: null }).detail).toMatch(/y sin asientos\.$/);
    expect(ledgerExplain({ ...BAG, tenant_name: null }).what).toBe("Bolsa de un cliente");
    expect(ledgerExplain(ACCOUNT)).toEqual({
      what: "Cuenta del partner",
      detail: "El libro de la cuenta sacó 100,00\u00a0USD para las bolsas; los traspasos dicen 90,00001\u00a0USD.",
    });
  });

  it("says whether Meta delivered more than is stored, or less", () => {
    expect(metaExplain(MISSING)).toBe("Faltan 3 mensajes por guardar");
    expect(metaExplain({ ...MISSING, diff: 1 })).toBe("Falta 1 mensaje por guardar");
    expect(metaExplain(EXTRA)).toBe("Hay 1 mensaje guardado de más");
  });

  it("counts every kind, and leaves unread what could not be read", () => {
    expect(anomalyTotals(ROUTER, { ledger: [BAG, ACCOUNT], meta: [MISSING] })).toEqual({
      reserve: 1,
      noModel: 1,
      waiting: 4,
      ledger: 2,
      meta: 1,
    });
    expect(anomalyTotals(null, null)).toEqual({ reserve: null, noModel: null, waiting: null, ledger: null, meta: null });
  });
});

describe("the reconciliations", () => {
  it("lists the ledger's differences with the partner and where", () => {
    render(<LedgerDiffs rows={[BAG, ACCOUNT]} />);
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByRole("link", { name: "Demo Auditoría" }).getAttribute("href")).toBe(`/partners/${P1}/money`);
    expect(within(rows[1]!).getByRole("link", { name: "Bolsa de Volumen 03" }).getAttribute("href")).toBe(`/tenants/${T1}`);
    expect(within(rows[2]!).getByText("Cuenta del partner")).toBeTruthy();
  });

  it("says when the ledger adds up", () => {
    render(<LedgerDiffs rows={[]} />);
    expect(screen.getByText("El libro cuadra")).toBeTruthy();
  });

  it("lists the days Meta and the stored messages disagree, with the business's number", () => {
    render(<MetaDiffs rows={[MISSING, EXTRA]} />);
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByText("120")).toBeTruthy();
    expect(within(rows[1]!).getByText("117")).toBeTruthy();
    expect(within(rows[1]!).getByText("Faltan 3 mensajes por guardar")).toBeTruthy();
    expect(within(rows[1]!).getByRole("link", { name: "+34600000001" }).getAttribute("href")).toBe(`/tenants/${T1}/channels/${CH}`);
    expect(within(rows[2]!).getByText("Hay 1 mensaje guardado de más")).toBeTruthy();
    expect(within(rows[2]!).getByRole("link", { name: "Canal sin número" })).toBeTruthy();
  });

  it("says when Meta and the database agree", () => {
    render(<MetaDiffs rows={[]} />);
    expect(screen.getByText("Meta y la base coinciden")).toBeTruthy();
  });
});
