import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RouterAnomalies, RouterPreview, RouterProfile } from "@/lib/backend-models";

const h = vi.hoisted(() => ({ save: vi.fn(), preview: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  saveProfileAction: (...a: unknown[]) => h.save(...a),
  previewAction: (...a: unknown[]) => h.preview(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { ProfileEditor } = await import("../profile-editor");
const { RoutePreview } = await import("../route-preview");
const { AnomaliesView } = await import("../anomalies/anomalies-view");

const AUTO: RouterProfile = {
  profile: "auto",
  version: 3,
  published_by: "migration:0182",
  reason: "v1 del contrato",
  published_at: "2026-10-27T10:00:00Z",
  policy: {
    tasks: {
      classify: { min_quality: 0.9, max_cost_per_call_micros: 200, escalate_to: null, reasoning: "none", judge_sampling: null, reserve: null },
    },
    turn_cost_ceiling_micros: 80000,
    max_calls_per_turn: 12,
    max_escalations_per_hour: 3,
  },
};
const ECONOMY: RouterProfile = { ...AUTO, profile: "economy", version: 1 };
const CEILINGS = { max_calls_per_turn: 12, max_escalations_per_hour: 3 };
const TASKS = [
  { code: "classify", conversation: false, needs: ["strict_structured_outputs"] },
  { code: "answer", conversation: true, needs: ["context_window"] },
];

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

/** Spec 047 (T150, 40.13, 54.2): a change is a new version with its reason. */
describe("the profile editor", () => {
  it("shows who published the version in force and why", () => {
    render(<ProfileEditor profiles={[AUTO, ECONOMY]} ceilings={CEILINGS} deployments={[]} />);
    expect(screen.getByText(/versión 3/)).toBeTruthy();
    expect(screen.getByText(/migration:0182/)).toBeTruthy();
    expect(screen.getByText(/v1 del contrato/)).toBeTruthy();
  });

  it("does not save without a reason, and saves a new version with it", async () => {
    h.save.mockResolvedValue({ ok: true, data: { ...AUTO, version: 4 } });
    render(<ProfileEditor profiles={[AUTO, ECONOMY]} ceilings={CEILINGS} deployments={["openai/gpt-5.6-luna"]} />);
    const quality = screen.getByRole("textbox", { name: "Calidad mínima de classify" });
    await userEvent.clear(quality);
    await userEvent.type(quality, "0.93");
    const save = screen.getByRole("button", { name: "Publicar versión nueva" });
    await userEvent.click(save);
    expect(h.save).not.toHaveBeenCalled();
    expect(screen.getByText("Hace falta el motivo.")).toBeTruthy();

    await userEvent.type(screen.getByRole("textbox", { name: /Motivo/ }), "Se equivoca con los audios");
    await userEvent.click(save);
    expect(h.save).toHaveBeenCalledTimes(1);
    const [profile, body] = h.save.mock.calls[0] as [string, { policy: { tasks: Record<string, { min_quality: number }> }; reason: string }];
    expect(profile).toBe("auto");
    expect(body.reason).toBe("Se equivoca con los audios");
    expect(body.policy.tasks.classify!.min_quality).toBe(0.93);
    expect(h.refresh).toHaveBeenCalled();
  });

  it("switches profile without carrying the edits over", async () => {
    render(<ProfileEditor profiles={[AUTO, ECONOMY]} ceilings={CEILINGS} deployments={[]} />);
    await userEvent.click(screen.getByRole("button", { name: "Económico" }));
    expect(screen.getByRole("button", { name: "Económico" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/versión 1/)).toBeTruthy();
  });

  it("has an empty state", () => {
    render(<ProfileEditor profiles={[]} ceilings={CEILINGS} deployments={[]} />);
    expect(screen.getByText("No hay perfiles publicados")).toBeTruthy();
  });
});

const PREVIEW: RouterPreview = {
  task: "answer",
  conversation: true,
  profile: "auto",
  policy_version: 3,
  outcome: "no_model",
  chain: [],
  rejected: [
    { deployment: "anthropic/claude-haiku-4-5", reason: "retention" },
    { deployment: "bedrock/eu.haiku", reason: "status" },
  ],
  estimated_cost_micros: null,
  facts: { eu_only: true, sovereign: false, partner_allowed: [], agent_certified: [], degraded: false },
};

describe("the route preview", () => {
  it("says what the router would choose, and why every other was discarded", async () => {
    h.preview.mockResolvedValue({ ok: true, data: PREVIEW });
    render(<RoutePreview tasks={TASKS} profiles={["auto", "economy"]} />);
    await userEvent.type(screen.getByRole("textbox", { name: /Cliente/ }), "11111111-1111-4111-8111-111111111111");
    await userEvent.click(screen.getByRole("button", { name: "Ver qué elegiría" }));
    expect(h.preview).toHaveBeenCalledWith({
      tenant_id: "11111111-1111-4111-8111-111111111111",
      task: "classify",
    });
    const result = screen.getByRole("region", { name: "Resultado" });
    expect(within(result).getByText("Sin modelo disponible")).toBeTruthy();
    expect(within(result).getByText(/retención cero/)).toBeTruthy();
    expect(within(result).getByText(/Solo UE/)).toBeTruthy();
  });

  it("refuses an id that is not one", async () => {
    render(<RoutePreview tasks={TASKS} profiles={["auto"]} />);
    await userEvent.type(screen.getByRole("textbox", { name: /Cliente/ }), "barberia");
    await userEvent.click(screen.getByRole("button", { name: "Ver qué elegiría" }));
    expect(h.preview).not.toHaveBeenCalled();
    expect(screen.getByText(/identificador del cliente/)).toBeTruthy();
  });
});

const ANOMALIES: RouterAnomalies = {
  since: "2026-10-20T00:00:00Z",
  items: [
    { tenant_id: "t1", tenant_name: "Barbería Sol", task: "answer", kind: "no_model", decision_id: "d1", created_at: "2026-10-27T09:00:00Z" },
    { tenant_id: "t2", tenant_name: "Clínica Mar", task: "classify", kind: "reserve_model", decision_id: null, created_at: "2026-10-26T09:00:00Z" },
  ],
  waiting_no_model: [{ tenant_id: "t1", tenant_name: "Barbería Sol", conversations: 3 }],
};

describe("the anomalies", () => {
  it("lists reserve models and no-model decisions, and who waits in the Inbox", () => {
    render(<AnomaliesView data={ANOMALIES} />);
    expect(screen.getByText(/3 conversaciones/)).toBeTruthy();
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByText("Barbería Sol")).toBeTruthy();
    expect(within(rows[1]!).getByText("Sin modelo disponible")).toBeTruthy();
    expect(within(rows[2]!).getByText(/reserva/)).toBeTruthy();
  });

  it("has an empty state", () => {
    render(<AnomaliesView data={{ ...ANOMALIES, items: [], waiting_no_model: [] }} />);
    expect(screen.getByText("Sin anomalías en este periodo")).toBeTruthy();
    // Un vacío de solo lectura (recorrido UI: salía el aviso de desarrollo del sistema de diseño).
    expect(screen.queryByText(/EmptyState without action/)).toBeNull();
  });
});
