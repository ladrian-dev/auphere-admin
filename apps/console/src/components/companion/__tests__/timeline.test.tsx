import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { type CompanionState, companionReducer, emptyCompanionState } from "../state";
import { Timeline } from "../timeline";
import * as f from "./fixtures";

function build(runId: string, events: ReturnType<typeof f.ev>[], base = emptyCompanionState): CompanionState {
  return events.reduce((s, ev) => companionReducer(s, { type: "event", runId, ev, now: 1_000 }), base);
}

const SUGGESTIONS = ["¿Por qué bajó la calidad de este número?", "¿Hay plantillas rechazadas y por qué?", "¿Este canal está bien conectado?"];

function renderTimeline(overrides: Partial<React.ComponentProps<typeof Timeline>> = {}) {
  const props: React.ComponentProps<typeof Timeline> = {
    state: emptyCompanionState,
    status: "ready",
    errorDetail: null,
    partial: false,
    currentUserId: "user_a_ab12cd34",
    deciding: false,
    decisionFailure: null,
    suggestions: SUGGESTIONS,
    onRetry: vi.fn(),
    onSuggestion: vi.fn(),
    onAnswerSlot: vi.fn(),
    onDecide: vi.fn(),
    ...overrides,
  };
  render(
    <LocaleProvider locale="es">
      <Timeline {...props} />
    </LocaleProvider>,
  );
  return props;
}

/** The five Hurff states — the workspace floor, measured not asserted. */
describe("Timeline — the five states", () => {
  it("LOADING renders skeleton bubbles, not a spinner", () => {
    renderTimeline({ status: "loading" });
    const log = screen.getByRole("log");
    expect(log).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText("Cargando la conversación…")).toBeInTheDocument();
  });

  it("EMPTY offers the three suggestions derived from the page, not generic ones", async () => {
    const user = userEvent.setup();
    const props = renderTimeline({ status: "ready" });
    expect(screen.getByText("¿En qué te echo una mano?")).toBeInTheDocument();
    for (const s of SUGGESTIONS) expect(screen.getByRole("button", { name: s })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: SUGGESTIONS[0] }));
    expect(props.onSuggestion).toHaveBeenCalledWith(SUGGESTIONS[0]);
  });

  it("ERROR gives the reason and a retry", async () => {
    const user = userEvent.setup();
    const props = renderTimeline({ status: "error", errorDetail: "network" });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("No se pudo cargar la conversación")).toBeInTheDocument();
    expect(screen.getByText(/El trabajo del Companion sigue en marcha/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(props.onRetry).toHaveBeenCalled();
  });

  it("PARTIAL shows what is already done AND says the rest is elsewhere", () => {
    const state = build("run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "voy por aquí")]);
    renderTimeline({ state, partial: true });
    expect(screen.getByText("voy por aquí")).toBeInTheDocument();
    expect(screen.getByText("Falta parte de esta conversación")).toBeInTheDocument();
  });

  it("IDEAL renders the whole turn: thinking, tool, plan, verification", () => {
    const state = build("run-a", [
      f.runStarted(1, "run-a"),
      f.reasoningDelta(2, "déjame mirar"),
      f.toolStarted(3, "t1"),
      f.toolCompleted(4, "t1"),
      f.planProposed(5),
      f.verifyResult(6, "9c1e", true),
      f.textDelta(7, "listo"),
      f.runCompleted(8, "run-a"),
    ]);
    renderTimeline({ state });
    expect(screen.getByText("Consultando el consumo de Boreal")).toBeInTheDocument();
    expect(screen.getByText("Plan propuesto")).toBeInTheDocument();
    expect(screen.getByText("Ajustar el prompt de Clínica Boreal")).toBeInTheDocument();
    expect(screen.getByText("Lo que comprobé después")).toBeInTheDocument();
    expect(screen.getByText("listo")).toBeInTheDocument();
    expect(screen.getByText(/Pensó/)).toBeInTheDocument();
  });
});

describe("Timeline — live regions (§14)", () => {
  it("keeps the log polite so streamed text does not interrupt", () => {
    renderTimeline({ state: build("run-a", [f.textDelta(1, "hola")]) });
    expect(screen.getByRole("log")).toHaveAttribute("aria-live", "polite");
  });

  it("uses assertive ONLY for a pending hitl.requested", () => {
    // Nothing pending → the assertive region exists but is silent.
    renderTimeline({ state: build("run-a", [f.textDelta(1, "hola")]) });
    const assertive = document.querySelector('[aria-live="assertive"]');
    expect(assertive).toBeTruthy();
    expect(assertive?.textContent).toBe("");
  });

  it("announces the confirmation assertively when one is pending", () => {
    renderTimeline({ state: build("run-a", [f.hitlRequested(1)]) });
    const assertive = document.querySelector('[aria-live="assertive"]');
    expect(assertive?.textContent).toContain("Publicar la v8 del agente de Clínica Boreal");
  });

  it("stops announcing once the card is sealed", () => {
    let state = build("run-a", [f.hitlRequested(1)]);
    state = build("run-b", [f.hitlResolved(1)], state);
    renderTimeline({ state });
    expect(document.querySelector('[aria-live="assertive"]')?.textContent).toBe("");
  });
});

describe("Timeline — the intake is chips, not a form", () => {
  it("has no form and drops the slot into the composer when clicked", async () => {
    const user = userEvent.setup();
    const props = renderTimeline({ state: build("run-a", [f.intakeMissing(1)]) });
    expect(document.querySelector("form")).toBeNull();
    const chip = screen.getByRole("button", { name: /Responder «Qué NO debe hacer el agente»/ });
    await user.click(chip);
    expect(props.onAnswerSlot).toHaveBeenCalledWith(expect.objectContaining({ key: "forbidden_behaviour" }));
    expect(screen.getByText(/No dar precios por WhatsApp/)).toBeInTheDocument();
  });
});

describe("Timeline — reasoning is collapsed by default (§8.2)", () => {
  it("hides the reasoning behind a one-click disclosure", async () => {
    const user = userEvent.setup();
    const state = build("run-a", [f.reasoningDelta(1, "razonamiento privado"), f.textDelta(2, "respuesta")]);
    renderTimeline({ state });
    expect(screen.queryByText("razonamiento privado")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { expanded: false, name: /Pensó/ }));
    expect(screen.getByText("razonamiento privado")).toBeInTheDocument();
    expect(screen.getByText(/no se guarda/)).toBeInTheDocument();
  });
});

describe("Timeline — the tool card never shows a customer's message body", () => {
  it("discloses the request and explains why there is no raw response", async () => {
    const user = userEvent.setup();
    renderTimeline({ state: build("run-a", [f.toolStarted(1, "t1"), f.toolCompleted(2, "t1", true, "c1"), f.citation(3, "c1")]) });
    await user.click(screen.getByRole("button", { name: "Ver petición y respuesta" }));
    // The raw request is disclosed…
    expect(document.querySelector("pre")?.textContent).toContain("client_ref");
    // …and the absence of a raw response is explained, not left blank: the
    // tool result never travels over the stream (decision C8).
    expect(screen.getByText(/no viaja por el directo/)).toBeInTheDocument();
    // The citation stays visible with its provenance.
    expect(screen.getByText("Consumo del partner (client_ref=boreal)")).toBeInTheDocument();
  });
});
