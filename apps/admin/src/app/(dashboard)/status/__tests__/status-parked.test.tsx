import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RouterAnomalies } from "@/lib/backend-models";

import { summaryItems } from "../anomalies";

/**
 * Spec 059 (historia 2; 2.4, 2.6, 2.7): parked, Estado has no Router block,
 * none of its three figures and no link to Router; the rest stays the same.
 */
const flag = vi.hoisted(() => ({ visible: false }));
vi.mock("@/lib/router-panel", () => ({
  get ROUTER_PANEL_VISIBLE() {
    return flag.visible;
  },
}));

const api = vi.hoisted(() => ({ getInstance: vi.fn(), reconciliations: vi.fn(), anomalies: vi.fn() }));
vi.mock("@/lib/backend", () => ({ backend: { getInstance: api.getInstance } }));
vi.mock("@/lib/backend-levers", () => ({ leversBackend: { reconciliations: api.reconciliations } }));
vi.mock("@/lib/backend-models", () => ({ modelsBackend: { anomalies: api.anomalies } }));

const { default: StatusPage } = await import("../page");

const ROUTER: RouterAnomalies = {
  items: [
    { tenant_id: "t1", tenant_name: "Volumen 03", task: "conversation", kind: "reserve_model", decision_id: "d1", created_at: "2026-10-27T10:00:00Z" },
  ],
  waiting_no_model: [{ tenant_id: "t1", tenant_name: "Volumen 03", conversations: 4 }],
  since: "2026-10-21T00:00:00Z",
};

beforeEach(() => {
  api.getInstance.mockReset().mockResolvedValue({
    environment: "staging",
    schema_revision: "0231",
    commit: "abcdef1234567890",
    checks: { postgres: "ok", redis: "ok" },
    meta_graph_version: null,
    meta_graph_expires_on: null,
    meta_graph_days_left: null,
  });
  api.reconciliations.mockReset().mockResolvedValue({ ledger: [], meta: [] });
  api.anomalies.mockReset().mockResolvedValue(ROUTER);
});

async function page() {
  render(await StatusPage({ searchParams: Promise.resolve({}) }));
}

const ROUTER_TERMS = ["Con modelo de reserva", "Sin modelo", "Esperan por «Sin modelo disponible»"];

describe("Estado, with the router parked", () => {
  beforeEach(() => {
    flag.visible = false;
  });

  it("has no Router block, none of its figures and no link to it", async () => {
    await page();
    expect(screen.queryByRole("heading", { name: "Router" })).toBeNull();
    for (const term of ROUTER_TERMS) expect(screen.queryByText(term)).toBeNull();
    expect(screen.queryByRole("link", { name: "Abrir en Router" })).toBeNull();
    for (const link of screen.queryAllByRole("link")) {
      expect(link.getAttribute("href") ?? "").not.toMatch(/^\/(router|certifications)/);
    }
    expect(api.anomalies).not.toHaveBeenCalled();
  });

  it("keeps the rest of Estado as it was", async () => {
    await page();
    expect(screen.getByText("Diferencias del libro")).toBeTruthy();
    expect(screen.getByText("Días con diferencias con Meta")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Libro de las bolsas" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Mensajes de Meta" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Despliegue" })).toBeTruthy();
  });
});

describe("Estado, with the router visible", () => {
  beforeEach(() => {
    flag.visible = true;
  });

  it("shows the Router block, its three figures and its link, as before", async () => {
    await page();
    expect(screen.getByRole("heading", { name: "Router" })).toBeTruthy();
    for (const term of ROUTER_TERMS) expect(screen.getByText(term)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Abrir en Router" }).getAttribute("href")).toBe("/router/anomalies");
    expect(api.anomalies).toHaveBeenCalled();
  });
});

describe("the summary of anomalies", () => {
  const totals = { reserve: 1, noModel: 2, waiting: 4, ledger: 0, meta: 3 };

  it("parked, keeps only the ledger and Meta", () => {
    expect(summaryItems(totals, false).map((i) => i.key)).toEqual(["ledger", "meta"]);
  });

  it("visible, has the five figures in their order", () => {
    expect(summaryItems(totals, true).map((i) => i.key)).toEqual(["reserve", "no_model", "waiting", "ledger", "meta"]);
    expect(summaryItems({ ...totals, ledger: null }, true).find((i) => i.key === "ledger")?.detail).toBe("Sin leer");
  });
});
