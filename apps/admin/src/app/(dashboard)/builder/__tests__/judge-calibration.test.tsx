import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CalibrationReport } from "@/lib/backend-builder";

const h = vi.hoisted(() => ({ calibrate: vi.fn(), success: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("../actions", () => ({
  calibrateJudgeAction: (...a: unknown[]) => h.calibrate(...a),
  publishSectorTestsAction: vi.fn(),
  runEvalAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh, replace: h.replace }) }));

const { CalibrationView } = await import("../judge-calibration/calibration-view");
const { RunCalibration } = await import("../judge-calibration/run-calibration");
const { agreementOf, blockingCalibration, calibrationState, formatShare } = await import("../labels");

const ITEMS = [
  { id: "cal-01", key: "hours", label: "pass", judge: "pass", match: true },
  { id: "cal-02", key: "price", label: "fail", judge: "pass", match: false },
  { id: "cal-03", key: "handoff", label: "unknown", judge: "unknown", match: true },
  { id: "cal-04", key: "booked", label: "pass", judge: "unknown", match: false },
] as const;

/** As `GET /admin/builder/judge-calibration` sends it: `quality` is a decimal string. */
const POOR: CalibrationReport = {
  deployment_id: "d-gpt",
  model_id: "openai/gpt-5.6-luna",
  quality: "0.5000",
  passed: false,
  scores: { agreement: 0.5, threshold: 0.85, set_version: 1, items: [...ITEMS] },
  certified_at: "2026-10-27T10:00:00Z",
  invalidated_at: null,
};
const GOOD: CalibrationReport = {
  ...POOR,
  deployment_id: "d-mistral",
  model_id: "mistral/large-eu",
  quality: "0.9130",
  passed: true,
  scores: { agreement: 0.913, threshold: 0.85, set_version: 1, items: [] },
  certified_at: "2026-10-26T10:00:00Z",
};

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

/** Spec 047 (T087, 21.8): the judge does not block until it agrees with people. */
describe("the judge's calibration", () => {
  it("reads the agreement whether it comes as a number or as a decimal string", () => {
    expect(agreementOf(POOR)).toBe(0.5);
    expect(agreementOf({ ...GOOD, scores: {} })).toBeCloseTo(0.913);
    expect(formatShare(0.913).replace(/\s/g, " ")).toBe("91,3 %");
  });

  it("only a passed calibration still in force lets the judge block", () => {
    expect(calibrationState(POOR)).toEqual({ label: "Suspendida", tone: "danger" });
    expect(calibrationState(GOOD)).toEqual({ label: "Aprobada", tone: "positive" });
    expect(calibrationState({ ...GOOD, invalidated_at: "2026-10-27T11:00:00Z" }).label).toBe("Caducada");
    expect(blockingCalibration([POOR])).toBeNull();
    expect(blockingCalibration([POOR, { ...GOOD, invalidated_at: "2026-10-27T11:00:00Z" }])).toBeNull();
    expect(blockingCalibration([POOR, GOOD])).toBe(GOOD);
  });

  it("says the judge does not block yet, and shows the agreement against the threshold", () => {
    render(<CalibrationView reports={[POOR]} />);
    expect(screen.getByText("El juez todavía no bloquea ninguna publicación")).toBeTruthy();
    expect(screen.getByText(/se decide solo por el estado final/)).toBeTruthy();
    expect(screen.getByText("Informe de openai/gpt-5.6-luna")).toBeTruthy();
    const meter = screen.getByRole("progressbar", { name: "Acuerdo con las etiquetas humanas" });
    expect(meter.getAttribute("aria-valuetext")?.replace(/\s/g, " ")).toBe("50 % · umbral 85 %");
    expect(meter.getAttribute("value")).toBe("50");
    expect(screen.getByText(/2 de 4 criterios coinciden/)).toBeTruthy();
    const table = screen.getByRole("table", { name: "Ejemplos de la calibración" });
    const row = within(table).getAllByRole("row")[2]!;
    expect(within(row).getByText("cal-02")).toBeTruthy();
    expect(within(row).getByText("Falla")).toBeTruthy();
    expect(within(row).getByText("Pasa")).toBeTruthy();
    expect(within(row).getByText("No coincide")).toBeTruthy();
  });

  it("filters the disagreements", async () => {
    render(<CalibrationView reports={[POOR]} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Solo los desacuerdos (2)" }));
    const rows = within(screen.getByRole("table", { name: "Ejemplos de la calibración" })).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(screen.queryByText("cal-01")).toBeNull();
    expect(screen.getAllByText("No sé").length).toBeGreaterThan(0);
  });

  it("says the judge blocks once one deployment passed, and lists every calibration", () => {
    render(<CalibrationView reports={[POOR, GOOD]} selected="d-mistral" />);
    expect(screen.getByText("El juez ya puede bloquear una publicación")).toBeTruthy();
    expect(screen.getByText("Informe de mistral/large-eu")).toBeTruthy();
    const all = screen.getByRole("region", { name: "Todas las calibraciones" });
    expect(within(all).getByRole("link", { name: "openai/gpt-5.6-luna" }).getAttribute("href")).toBe(
      "/builder/judge-calibration?deployment=d-gpt",
    );
    expect(within(all).getByText("Aprobada")).toBeTruthy();
  });

  it("has an empty state", () => {
    render(<CalibrationView reports={[]} />);
    expect(screen.getByText("Todavía no se ha calibrado ningún juez")).toBeTruthy();
    expect(screen.getByText("El juez todavía no bloquea ninguna publicación")).toBeTruthy();
  });
});

describe("calibrating a deployment", () => {
  const DEPLOYMENTS = [
    { uuid: "u1", key: "openai/gpt-5.6-luna", status: "active" as const },
    { uuid: "u2", key: "mistral/large-eu", status: "draft" as const },
  ];

  it("runs the chosen deployment and opens its report", async () => {
    h.calibrate.mockResolvedValue({
      ok: true,
      data: { deployment_id: "u2", agreement: 0.913, threshold: 0.85, set_version: 1, items: [], passed: true },
    });
    render(<RunCalibration deployments={DEPLOYMENTS} />);
    await userEvent.click(screen.getByRole("button", { name: "Calibrar un despliegue" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("option", { name: "mistral/large-eu · Borrador" })).toBeTruthy();
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: /Despliegue/ }), "u2");
    await userEvent.click(within(dialog).getByRole("button", { name: "Calibrar" }));
    expect(h.calibrate).toHaveBeenCalledWith("u2");
    expect((h.success.mock.calls[0]![0] as string).replace(/\s/g, " ")).toBe("Calibración aprobada: 91,3 % de acuerdo");
    expect(h.replace).toHaveBeenCalledWith("/builder/judge-calibration?deployment=u2");
  });

  it("keeps the dialog open with the API's refusal", async () => {
    h.calibrate.mockResolvedValue({ ok: false, code: "unknown_deployment", error: "Ese despliegue ya no existe en el catálogo." });
    render(<RunCalibration deployments={DEPLOYMENTS} />);
    await userEvent.click(screen.getByRole("button", { name: "Calibrar un despliegue" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Calibrar" }));
    expect(within(dialog).getByRole("alert").textContent).toContain("ya no existe");
    expect(h.refresh).not.toHaveBeenCalled();
  });
});
