import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConsoleV2State, MigrationReport } from "@/lib/backend-levers";

const h = vi.hoisted(() => ({
  dryRun: vi.fn(),
  enable: vi.fn(),
  disable: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("../actions", () => ({
  consoleV2DryRunAction: (...a: unknown[]) => h.dryRun(...a),
  consoleV2EnableAction: (...a: unknown[]) => h.enable(...a),
  consoleV2DisableAction: (...a: unknown[]) => h.disable(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, warning: h.warning, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { ConsoleV2View } = await import("../console-v2-view");
const {
  CONSOLE_V2_ERRORS,
  agentLabel,
  agentVerdict,
  audienceText,
  channelChanges,
  clientLabel,
  diffFirst,
  enableGate,
  numberLabel,
  reasonFor,
  reportSummary,
  stateText,
} = await import("../console-v2");

const PARTNER = "pppppppp-0000-0000-0000-000000000001";
const T1 = "11111111-0000-0000-0000-000000000001";
const A1 = "aaaaaaaa-0000-0000-0000-000000000001";
const A2 = "aaaaaaaa-0000-0000-0000-000000000002";
const C1 = "cccccccc-0000-0000-0000-000000000001";
const C2 = "cccccccc-0000-0000-0000-000000000002";

const V1: ConsoleV2State = { version: "v1", enabled_at: null, enabled_by: null };
const V2: ConsoleV2State = { version: "v2", enabled_at: "2026-10-28T10:00:00Z", enabled_by: "operator:ana@auphere.com" };

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3_600_000).toISOString();

const SAME_AGENT = {
  tenant_id: T1,
  agent_id: A1,
  version_id: "v-1",
  same: true,
  prompt_identical: true,
  model_pinned: true,
  agent_name: "Recepción",
  client_name: "Volumen 03",
};
const SAME_NUMBER = {
  tenant_id: T1,
  channel_id: C1,
  before: { mode: "everyone", numbers: [] },
  after: { mode: "everyone", numbers: [], exceptions: [] },
  pending_migration: true,
  same: true,
  identifier: "+34600000001",
  client_name: "Volumen 03",
};

const clean = (hours: number, id = "r-clean"): MigrationReport => ({
  id,
  kind: "dry_run",
  status: "clean",
  agents: [SAME_AGENT],
  channels: [SAME_NUMBER],
  created_by: "operator:ana@auphere.com",
  reason: null,
  created_at: hoursAgo(hours),
});

const DIFF: MigrationReport = {
  id: "r-diff",
  kind: "dry_run",
  status: "diff",
  agents: [
    SAME_AGENT,
    { tenant_id: T1, agent_id: A2, version_id: "v-2", same: false, prompt_identical: false, model_pinned: true, agent_name: "Ventas", client_name: "Volumen 03" },
  ],
  channels: [
    SAME_NUMBER,
    {
      tenant_id: T1,
      channel_id: C2,
      before: { mode: "team_only", numbers: ["+34600000001", "+34600000002"] },
      after: { mode: "team_only", numbers: ["+34600000001"], exceptions: [] },
      pending_migration: false,
      same: false,
      identifier: "+34600000009",
      client_name: "Volumen 03",
    },
  ],
  created_by: "operator:luis@auphere.com",
  reason: "Revisión antes de activar",
  created_at: hoursAgo(2),
};

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

/** Spec 047 (T172; 55.2, 55.4, 55.5): the rules of the dry run and the switch. */
describe("the rules of the new console", () => {
  it("lets activate only with a clean dry run of the last 24 hours, like the API", () => {
    expect(enableGate([])).toMatchObject({ ok: false, code: "dry_run_required" });
    expect(enableGate([clean(25)])).toMatchObject({ ok: false, code: "dry_run_required" });
    expect(enableGate([DIFF])).toMatchObject({ ok: false, code: "dry_run_has_differences" });
    expect(enableGate([clean(1)])).toEqual({ ok: true });
    // An activation is not a dry run: the newest dry run decides.
    const activation = { ...clean(0.5, "r-act"), kind: "activation" as const, status: "diff" as const };
    expect(enableGate([activation, clean(1)])).toEqual({ ok: true });
  });

  it("says which console the partner sees today", () => {
    expect(stateText(V1)).toBe("Ve la consola de hoy.");
    expect(stateText(V2)).toMatch(/^Ve la consola nueva desde el .+ UTC \(la activó ana@auphere\.com\)\.$/);
  });

  it("asks a reason to switch, and takes it optional for the dry run", () => {
    expect(reasonFor("dry_run", "  ")).toBeNull();
    expect(reasonFor("dry_run", "ok")).toMatch(/al menos 3/);
    expect(reasonFor("enable", "")).toBe("Hace falta el motivo.");
    expect(reasonFor("disable", "")).toBe("Hace falta el motivo.");
    expect(reasonFor("enable", "Cliente listo")).toBeNull();
  });

  it("checks each agent's prompt, byte by byte, and its pinned model", () => {
    expect(agentVerdict(SAME_AGENT)).toMatchObject({ same: true, label: "Igual" });
    const changed = agentVerdict(DIFF.agents[1]!);
    expect(changed.same).toBe(false);
    expect(changed.checks).toEqual([
      { key: "prompt", label: "El prompt cambia", ok: false },
      { key: "model", label: "Modelo fijado", ok: true },
    ]);
    const noSpec = agentVerdict({ tenant_id: T1, agent_id: A1, version_id: "v", same: false, reason: "no_spec" });
    expect(noSpec).toMatchObject({ same: false, label: "Sin AgentSpec", checks: [] });
    expect(noSpec.note).toMatch(/no tiene AgentSpec/);
  });

  it("says who each number answers, before and after, and what changes", () => {
    expect(audienceText({ mode: "everyone", numbers: [] })).toBe("A todos");
    expect(audienceText({ mode: "everyone", numbers: [], exceptions: ["+1", "+2"] })).toBe("A todos, salvo 2 números");
    expect(audienceText({ mode: "team_only", numbers: ["+34600000001"] })).toBe("Solo mi equipo · +34600000001");
    expect(audienceText({ mode: "team_only", numbers: [] })).toBe("Solo mi equipo · ningún número");
    expect(channelChanges(DIFF.channels[1]!)).toEqual(["Salen: +34600000002."]);
    expect(channelChanges(SAME_NUMBER)).toEqual([]);
    expect(
      channelChanges({ ...SAME_NUMBER, after: { mode: "team_only", numbers: ["+34600000009"] }, same: false }),
    ).toEqual(["Pasa de «A todos» a «Solo mi equipo».", "Entran: +34600000009."]);
  });

  it("names each row with what the API sends, and its id when an old report has no name", () => {
    expect(clientLabel(SAME_AGENT)).toBe("Volumen 03");
    expect(agentLabel(SAME_AGENT)).toBe("Recepción");
    expect(numberLabel(SAME_NUMBER)).toBe("+34600000001");
    expect(clientLabel({ tenant_id: T1, client_name: null })).toBe("11111111…");
    expect(agentLabel({ ...SAME_AGENT, agent_name: undefined })).toBe("aaaaaaaa…");
    expect(numberLabel({ ...SAME_NUMBER, identifier: null })).toBe("cccccccc…");
  });

  it("counts the differences and puts them first", () => {
    expect(reportSummary(DIFF)).toEqual({ agents: 2, agentsDiff: 1, channels: 2, channelsDiff: 1, pending: 1 });
    expect(diffFirst(DIFF.agents).map((a) => a.agent_id)).toEqual([A2, A1]);
  });
});

describe("the new console screen", () => {
  const view = (reports: MigrationReport[], state: ConsoleV2State | null = V1) =>
    render(<ConsoleV2View partnerId={PARTNER} partnerName="Demo Auditoría" reports={reports} state={state} />);

  it("says which console the partner sees, and offers only the switch that applies", () => {
    const { unmount } = view([clean(1)], V1);
    expect(screen.getByRole("status").textContent).toContain("Ve la consola de hoy.");
    expect(screen.getByRole("button", { name: "Activar la consola nueva" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Volver a la consola de hoy" })).toBeNull();
    unmount();
    const second = view([clean(1)], V2);
    expect(screen.getByRole("status").textContent).toContain("Ve la consola nueva desde");
    expect(screen.queryByRole("button", { name: "Activar la consola nueva" })).toBeNull();
    expect(screen.getByRole("button", { name: "Volver a la consola de hoy" })).toBeTruthy();
    second.unmount();
    view([], null);
    expect(screen.getByText("No se pudo leer qué consola ve hoy el partner.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Activar la consola nueva" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Volver a la consola de hoy" })).toBeTruthy();
  });

  it("shows the newest report, named by the API, with its reason and the differences first and marked", () => {
    view([DIFF]);
    expect(screen.getByText("No se puede activar con este informe")).toBeTruthy();
    expect(screen.getByText("Motivo: «Revisión antes de activar»")).toBeTruthy();
    const agents = within(screen.getByRole("region", { name: "Agentes" })).getAllByRole("row");
    expect(within(agents[1]!).getByText("Ventas")).toBeTruthy();
    expect(within(agents[1]!).getByText("Volumen 03")).toBeTruthy();
    expect(within(agents[1]!).getByText("El prompt cambia")).toBeTruthy();
    expect(agents[1]!.getAttribute("data-diff")).toBe("true");
    expect(agents[2]!.getAttribute("data-diff")).toBeNull();
    const numbers = within(screen.getByRole("region", { name: "Números" })).getAllByRole("row");
    expect(within(numbers[1]!).getByRole("link", { name: "+34600000009" }).getAttribute("href")).toBe(`/tenants/${T1}/channels/${C2}`);
    expect(within(numbers[1]!).getByText("Solo mi equipo · +34600000001, +34600000002")).toBeTruthy();
    expect(within(numbers[1]!).getByText("Salen: +34600000002.")).toBeTruthy();
    expect(within(numbers[2]!).getByText("Sin migrar: la activación la guarda así.")).toBeTruthy();
  });

  it("does not let activate without a clean dry run of the last 24 hours, and says why", () => {
    const { unmount } = view([DIFF]);
    expect((screen.getByRole("button", { name: "Activar la consola nueva" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/El último ensayo tiene diferencias/)).toBeTruthy();
    unmount();
    const second = view([clean(30)]);
    expect((screen.getByRole("button", { name: "Activar la consola nueva" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Falta un ensayo de las últimas 24 horas/)).toBeTruthy();
    second.unmount();
    view([]);
    expect(screen.getByText("Todavía no hay ningún ensayo")).toBeTruthy();
  });

  it("runs the dry run with an optional reason and reloads the reports", async () => {
    h.dryRun.mockResolvedValue({ ok: true, data: { status: "diff", agents: [], channels: [] } });
    view([]);
    await userEvent.click(screen.getByRole("button", { name: "Correr el ensayo" }));
    let dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Correr el ensayo" }));
    expect(h.dryRun).toHaveBeenCalledWith(PARTNER, null);
    expect(h.warning).toHaveBeenCalledWith("El ensayo encontró diferencias");
    expect(h.refresh).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Correr el ensayo" }));
    dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Antes de activar");
    await userEvent.click(within(dialog).getByRole("button", { name: "Correr el ensayo" }));
    expect(h.dryRun).toHaveBeenLastCalledWith(PARTNER, "Antes de activar");
  });

  it("activates only with a reason, and says the API's refusal in words", async () => {
    h.enable
      .mockResolvedValueOnce({ ok: false, code: "dry_run_required", error: CONSOLE_V2_ERRORS.dry_run_required })
      .mockResolvedValueOnce({ ok: true, data: V2 });
    view([clean(1)]);
    await userEvent.click(screen.getByRole("button", { name: "Activar la consola nueva" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Activar" }));
    expect(h.enable).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Hace falta el motivo.")).toBeTruthy();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Cliente listo");
    await userEvent.click(within(dialog).getByRole("button", { name: "Activar" }));
    expect(h.enable).toHaveBeenCalledWith(PARTNER, "Cliente listo");
    expect(within(dialog).getByRole("alert").textContent).toContain("Falta un ensayo de las últimas 24 horas");
    expect(h.refresh).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Activar" }));
    expect(h.success).toHaveBeenCalledWith("Demo Auditoría ya ve la consola nueva");
    expect(screen.getByRole("status").textContent).toContain("Ve la consola nueva desde");
    expect(screen.getByRole("button", { name: "Volver a la consola de hoy" })).toBeTruthy();
    expect(h.refresh).toHaveBeenCalled();
  });

  it("goes back to today's console with a reason, only until the partner confirms the split", async () => {
    h.disable.mockResolvedValue({ ok: false, code: "wallet_split_confirmed", error: CONSOLE_V2_ERRORS.wallet_split_confirmed });
    view([clean(1)], V2);
    await userEvent.click(screen.getByRole("button", { name: "Volver a la consola de hoy" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "El partner lo pidió");
    await userEvent.click(within(dialog).getByRole("button", { name: "Volver a la consola de hoy" }));
    expect(h.disable).toHaveBeenCalledWith(PARTNER, "El partner lo pidió");
    expect(within(dialog).getByRole("alert").textContent).toContain("ya confirmó el reparto en bolsas");
  });

  it("keeps the history, with each reason, and opens an older report", async () => {
    view([clean(1), DIFF]);
    expect(screen.getByRole("heading", { name: "Último informe" })).toBeTruthy();
    expect(screen.queryByText("No se puede activar con este informe")).toBeNull();
    expect(screen.getByTitle("Revisión antes de activar")).toBeTruthy();
    const rows = screen.getAllByRole("button", { name: /Ver el informe del/ });
    expect(rows).toHaveLength(2);
    expect((rows[0] as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(rows[1]!);
    expect(screen.getByRole("heading", { name: "Informe elegido" })).toBeTruthy();
    expect(screen.getByText("No se puede activar con este informe")).toBeTruthy();
  });
});
