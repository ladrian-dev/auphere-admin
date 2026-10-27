import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Certifications } from "@/lib/backend-models";

const h = vi.hoisted(() => ({ launch: vi.fn() }));
vi.mock("../actions", () => ({ launchCertificationAction: (...a: unknown[]) => h.launch(...a) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { CertificationsView } = await import("../certifications-view");
const { RunCertification } = await import("../run-certification");
const { formatQuality, validity } = await import("../labels");

const DATA: Certifications = {
  battery_version: 1,
  by_deployment: [
    {
      deployment: "bedrock/eu.haiku",
      task: "classify",
      battery_version: 1,
      quality: 0.953,
      passed: true,
      scores: { metrics: { pass3: 0.97, latency_p95_ms: 640 }, threshold: 0.9 },
      certified_at: "2026-10-20T10:00:00Z",
      invalidated_at: null,
    },
    {
      deployment: "bedrock/eu.haiku",
      task: "answer",
      battery_version: 1,
      quality: 0.88,
      passed: true,
      scores: {},
      certified_at: "2026-10-10T10:00:00Z",
      invalidated_at: "2026-10-21T10:00:00Z",
    },
  ],
  by_agent: [
    {
      tenant_id: "t1",
      tenant_name: "Barbería Sol",
      agent_id: "a1",
      agent_name: "Reservas",
      deployment: "bedrock/eu.haiku",
      agent_config_id: "v1",
      suite_revision: 2,
      passed: false,
      paid_by: "partner",
      result: {},
      certified_at: "2026-10-22T10:00:00Z",
      invalidated_at: null,
    },
  ],
};

beforeEach(() => h.launch.mockReset());

/** Spec 047 (T150, 42.7, 54.3): certifications by deployment and by agent. */
describe("the certifications", () => {
  it("formats the quality and says whether each one still counts", () => {
    // Intl pone un espacio de no separación antes del «%».
    expect(formatQuality(0.953).replace(/\s/g, " ")).toBe("95,3 %");
    expect(validity(DATA.by_deployment[0]!)).toEqual({ label: "Vigente", tone: "positive" });
    expect(validity(DATA.by_deployment[1]!).label).toMatch(/^Caducada/);
    expect(validity({ ...DATA.by_deployment[0]!, passed: false })).toEqual({ label: "Suspendida", tone: "danger" });
  });

  it("shows the battery, the scores and the expiry by deployment, and the suite by agent", () => {
    render(<CertificationsView data={DATA} />);
    const byDeployment = screen.getByRole("region", { name: "Por despliegue" });
    const rows = within(byDeployment).getAllByRole("row");
    expect(within(rows[1]!).getByText("classify")).toBeTruthy();
    expect(within(rows[1]!).getByText("95,3 %")).toBeTruthy();
    expect(within(rows[1]!).getByText(/p95 640 ms/)).toBeTruthy();
    expect(within(rows[2]!).getByText(/Caducada/)).toBeTruthy();
    const byAgent = screen.getByRole("region", { name: "Por agente" });
    expect(within(byAgent).getByText("Reservas")).toBeTruthy();
    expect(within(byAgent).getByText("Barbería Sol")).toBeTruthy();
    expect(within(byAgent).getByText("Suspendida")).toBeTruthy();
    expect(within(byAgent).getByText(/Construcción y pruebas/)).toBeTruthy();
  });

  it("has empty states", () => {
    render(<CertificationsView data={{ battery_version: null, by_deployment: [], by_agent: [] }} />);
    expect(screen.getByText("Ninguna certificación por clase")).toBeTruthy();
    expect(screen.getByText("Ninguna certificación por agente")).toBeTruthy();
  });

  it("says why a certification cannot be launched yet", async () => {
    h.launch.mockResolvedValue({
      ok: false,
      code: "class_runner_offline",
      error: "La batería común corre fuera de línea hasta que tenga un trabajo de plataforma.",
    });
    render(<RunCertification deployments={[{ uuid: "d1", key: "bedrock/eu.haiku" }]} tasks={["classify", "answer"]} />);
    await userEvent.click(screen.getByRole("button", { name: "Lanzar una certificación" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "classify" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Lanzar" }));
    expect(h.launch).toHaveBeenCalledWith({ deployment_id: "d1", tasks: ["classify"] });
    expect(within(dialog).getByRole("alert").textContent).toContain("fuera de línea");
  });
});
