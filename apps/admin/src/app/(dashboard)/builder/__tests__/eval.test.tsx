import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EvalRun } from "@/lib/backend-builder";

const h = vi.hoisted(() => ({ run: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  runEvalAction: (...a: unknown[]) => h.run(...a),
  publishSectorTestsAction: vi.fn(),
  calibrateJudgeAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { EvalView } = await import("../eval/eval-view");
const { RunEval } = await import("../eval/run-eval");
const { evalDelta, formatMs, parseEvalLimit } = await import("../labels");

const OPERATOR = "11111111-2222-3333-4444-555555555555";
const FIRST: EvalRun = {
  id: "r1",
  bank_version: "v1",
  created_at: "2026-10-20T10:00:00Z",
  created_by: "operator:99999999-0000-0000-0000-000000000000",
  validator_first_pass_pct: 90,
  sector_pass_unedited_pct: null,
  draft_p90_ms: 14_200,
  vs_previous: null,
};
const LATEST: EvalRun = {
  id: "r2",
  bank_version: "v1",
  created_at: "2026-10-27T10:00:00Z",
  created_by: `operator:${OPERATOR}`,
  validator_first_pass_pct: 96,
  sector_pass_unedited_pct: null,
  draft_p90_ms: 12_000,
  vs_previous: { validator_first_pass_pct: 6, sector_pass_unedited_pct: null, draft_p90_ms: -2200 },
};

const plain = (text: string | null | undefined) => (text ?? "").replace(/\s/g, " ");

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

/** Spec 047 (T100, 54.4, CE-002, CE-003): the builder against the bank, compared with the last time. */
describe("the figures of the builder's evaluation", () => {
  it("says a change in points for the shares and in time for the p90, where down is good", () => {
    expect(evalDelta("validator_first_pass_pct", 6)).toMatchObject({ label: "+6 pts", tone: "positive" });
    expect(evalDelta("validator_first_pass_pct", -3.5)).toMatchObject({ label: "−3,5 pts", tone: "negative" });
    expect(plain(evalDelta("draft_p90_ms", -2200)?.label)).toBe("−2,2 s");
    expect(evalDelta("draft_p90_ms", -2200)?.tone).toBe("positive");
    expect(evalDelta("draft_p90_ms", 300)).toMatchObject({ label: "+300 ms", tone: "negative" });
    expect(evalDelta("validator_first_pass_pct", 0)?.tone).toBe("neutral");
    expect(evalDelta("validator_first_pass_pct", null)).toBeUndefined();
    expect(plain(formatMs(12_000))).toBe("12 s");
  });

  /** Spec 059 (5.6): the bank has the size the API says, not a fixed 100. */
  it("runs the whole bank when the number is empty, whatever its size", () => {
    expect(parseEvalLimit("", 120)).toEqual({ ok: true, limit: null });
    expect(parseEvalLimit("120", 120)).toEqual({ ok: true, limit: null });
    expect(parseEvalLimit("100", 120)).toEqual({ ok: true, limit: 100 });
    expect(parseEvalLimit(" 4 ", 120)).toEqual({ ok: true, limit: 4 });
    expect(parseEvalLimit("0", 120).ok).toBe(false);
    expect(parseEvalLimit("121", 120)).toEqual({ ok: false, error: "Un número entero entre 1 y 120, o vacío para todo el banco." });
    expect(parseEvalLimit("2.5", 120).ok).toBe(false);
  });
});

describe("the evaluation screen", () => {
  it("shows the last run against the one before and the targets", () => {
    render(<EvalView runs={[LATEST, FIRST]} bankSize={120} operatorId={OPERATOR} />);
    const last = screen.getByRole("region", { name: "La última evaluación" });
    expect(within(last).getByText(/banco v1 · Tú/)).toBeTruthy();
    expect(within(last).getByText("96 %")).toBeTruthy();
    expect(within(last).getByText("+6 pts")).toBeTruthy();
    expect(plain(within(last).getByText(/Objetivo 95 %/).textContent)).toBe("Objetivo 95 % · antes 90 %");
    expect(within(last).getByText("12 s")).toBeTruthy();
    expect(within(last).getByText("Mejor que la evaluación anterior: −2,2 s")).toBeTruthy();
    const history = screen.getByRole("region", { name: "Historial" });
    expect(within(history).getAllByRole("row")).toHaveLength(3);
    expect(within(history).getByText("Operador 99999999")).toBeTruthy();
  });

  /** Spec 059 (5.6): the evaluation does not measure the sector battery, so it does not show it. */
  it("does not show the sector battery figure it never measures", () => {
    render(<EvalView runs={[{ ...LATEST, sector_pass_unedited_pct: 80 }, FIRST]} bankSize={120} operatorId={OPERATOR} />);
    expect(screen.queryByText(/Batería/)).toBeNull();
    expect(screen.queryByText(/batería del sector/)).toBeNull();
    expect(screen.queryByText("80 %")).toBeNull();
    expect(screen.queryByText("Sin medir")).toBeNull();
    const history = screen.getByRole("region", { name: "Historial" });
    expect(within(history).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Fecha",
      "Banco",
      "Quién",
      "Validador a la primera",
      "p90 del borrador",
    ]);
  });

  it("says when there is nothing to compare with", () => {
    render(<EvalView runs={[FIRST]} bankSize={120} operatorId={OPERATOR} />);
    expect(screen.getByText("Es la primera: todavía no hay con qué compararla.")).toBeTruthy();
    expect(screen.queryByText(/pts/)).toBeNull();
  });

  it("has an empty state that says the real size of the bank", () => {
    render(<EvalView runs={[]} bankSize={120} operatorId={OPERATOR} />);
    expect(screen.getByText("Todavía no se ha corrido la evaluación")).toBeTruthy();
    expect(screen.getByText(/las 120 descripciones del banco/)).toBeTruthy();
    expect(screen.queryByText(/100/)).toBeNull();
  });
});

describe("running the evaluation", () => {
  it("checks the number of descriptions and runs it", async () => {
    h.run.mockResolvedValue({ ok: true, data: LATEST });
    render(<RunEval bankSize={120} />);
    await userEvent.click(screen.getByRole("button", { name: "Correr la evaluación" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/con las 120 tarda varios minutos/)).toBeTruthy();
    const count = within(dialog).getByRole("textbox", { name: /Descripciones/ });
    await userEvent.type(count, "500");
    await userEvent.click(within(dialog).getByRole("button", { name: "Correr" }));
    expect(h.run).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/entre 1 y 120/)).toBeTruthy();

    await userEvent.clear(count);
    await userEvent.type(count, "4");
    await userEvent.click(within(dialog).getByRole("button", { name: "Correr" }));
    expect(h.run).toHaveBeenCalledWith(4);
    expect(plain(h.success.mock.calls[0]![0] as string)).toBe("Evaluación guardada: 96 % pasa el validador a la primera");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("runs the whole bank by default", async () => {
    h.run.mockResolvedValue({ ok: true, data: LATEST });
    render(<RunEval bankSize={120} />);
    await userEvent.click(screen.getByRole("button", { name: "Correr la evaluación" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Correr" }));
    expect(h.run).toHaveBeenCalledWith(null);
  });
});
