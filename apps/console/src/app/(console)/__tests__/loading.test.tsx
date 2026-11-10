import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type MessageKey, t as translate } from "@/i18n/messages";

/**
 * Spec 045 (R6.5, T017): while a page loads, its skeleton has the page's
 * shape. The root `loading.tsx` is shared by the partner's home and the
 * client's Panel, and `/usage` by both Consumos: each person gets its own,
 * and the partner's does not change.
 */
const state = vi.hoisted(() => ({
  resolution: { kind: "anonymous" } as unknown,
  path: "/" as string | null,
}));

vi.mock("@/lib/principal", () => ({ resolvePrincipal: async () => state.resolution }));
vi.mock("next/headers", () => ({ headers: async () => new Headers(state.path ? { "x-pathname": state.path } : {}) }));
vi.mock("@/i18n/server", () => ({
  getT: async () => ({ locale: "es", t: (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars) }),
}));

const RootLoading = (await import("../loading")).default;
const UsageLoading = (await import("../usage/loading")).default;

const client = (modules: string[]) => ({
  kind: "ok",
  principal: { kind: "client", modules, locale: "es", clientName: "Flor y Encanto", name: "Valeria Ríos" },
});
const partner = { kind: "ok", principal: { kind: "partner", modules: ["panel", "usage"], locale: "es" } };

async function paint(loading: () => Promise<React.ReactElement>) {
  return render(await loading());
}

describe("loading skeletons", () => {
  beforeEach(() => {
    state.path = "/";
  });

  it("the client's Panel loads with the Panel's shape: spend, the three figures and the chart", async () => {
    state.resolution = client(["panel", "inbox", "usage"]);
    const { container } = await paint(RootLoading);
    expect(container.querySelector('[data-slot="lite-panel-skeleton"]')).not.toBeNull();
    expect(screen.getByRole("status", { name: "Cargando" })).toBeTruthy();
    for (const label of ["Gasto del mes", "Conversaciones", "Esperan a una persona", "Saldo disponible", "Conversaciones por día"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("without the inbox the Panel has no «waiting» figure, so neither does its skeleton", async () => {
    state.resolution = client(["panel", "usage"]);
    const { container } = await paint(RootLoading);
    expect(screen.queryByText("Esperan a una persona")).toBeNull();
    expect(container.querySelector('[data-slot="lite-reservas-skeleton"]')).toBeNull();
  });

  it("with Reservas the Panel's skeleton keeps the place of its block (spec 043, T026)", async () => {
    state.resolution = client(["panel", "inbox", "reservas", "usage"]);
    const { container } = await paint(RootLoading);
    expect(container.querySelector('[data-slot="lite-panel-skeleton"] [data-slot="lite-reservas-skeleton"]')).not.toBeNull();
  });

  it("the partner's home keeps its own skeleton", async () => {
    state.resolution = partner;
    const { container } = await paint(RootLoading);
    expect(container.querySelector('[data-slot="lite-panel-skeleton"]')).toBeNull();
    expect(container.querySelector('[data-slot="header-skeleton"]')).not.toBeNull();
  });

  it("a client's page without its own skeleton gets the plain one, not the Panel's", async () => {
    state.resolution = client(["panel", "inbox", "usage"]);
    state.path = "/account/phones";
    const { container } = await paint(RootLoading);
    expect(container.querySelector('[data-slot="lite-panel-skeleton"]')).toBeNull();
  });

  it("the client's Consumo loads with the balance first, then spend, conversations, the chart and the detail", async () => {
    state.resolution = client(["panel", "inbox", "usage"]);
    state.path = "/usage";
    const { container } = await paint(UsageLoading);
    const skeleton = container.querySelector('[data-slot="lite-usage-skeleton"]');
    expect(skeleton).not.toBeNull();
    const cards = skeleton?.querySelector('[data-slot="lite-usage-cards"]');
    expect(cards?.firstElementChild?.textContent).toContain("Saldo disponible");
    for (const label of ["Gasto del mes", "Conversaciones del mes", "Gasto por día", "Detalle técnico: mensajes, uso del modelo y multimedia"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("the partner's Consumo keeps the plain skeleton", async () => {
    state.resolution = partner;
    state.path = "/usage";
    const { container } = await paint(UsageLoading);
    expect(container.querySelector('[data-slot="lite-usage-skeleton"]')).toBeNull();
    expect(container.querySelector('[data-slot="header-skeleton"]')).not.toBeNull();
  });
});
