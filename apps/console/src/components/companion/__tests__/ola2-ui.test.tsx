import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { Composer } from "../composer";
import { ConfirmCard } from "../confirm-card";
import { type CompanionState, companionReducer, emptyCompanionState, trialClientRef } from "../state";
import { Timeline } from "../timeline";
import { TrialPanel } from "../trial-panel";
import { readTrial } from "../types";
import * as f from "./fixtures";

/**
 * The Ola 2 interface against **CONTRACT-V2**, rendered.
 *
 * The lesson of the Ola 1 was not "write the five states" — it was
 * **check each one is reachable**. A `status` that started at `"loading"`
 * and only became `"ready"` inside `openThread` meant the empty state
 * could never render at all, and it was written. So every state below is
 * reached through the real path, not asserted about in the abstract.
 */
function build(runId: string, events: ReturnType<typeof f.ev>[], base = emptyCompanionState): CompanionState {
  return events.reduce((s, ev) => companionReducer(s, { type: "event", runId, ev, now: 1_000 }), base);
}

function renderTimeline(state: CompanionState, locale: "es" | "en" = "es") {
  const props: React.ComponentProps<typeof Timeline> = {
    state,
    status: "ready",
    errorDetail: null,
    partial: false,
    currentUserId: "user_a_ab12cd34",
    deciding: false,
    decisionFailure: null,
    suggestions: [],
    onRetry: vi.fn(),
    onSuggestion: vi.fn(),
    onAnswerSlot: vi.fn(),
    onDecide: vi.fn(),
  };
  render(
    <LocaleProvider locale={locale}>
      <Timeline {...props} />
    </LocaleProvider>,
  );
  return props;
}

// ── §3 · the intake chips ──────────────────────────────────────────────

describe("intake chips — `work_kind` and the field nobody writes (v2 §3)", () => {
  it("titles the group from `work_kind`, not from a generic heading", () => {
    renderTimeline(build("run-a", [f.intakeCreateClient(1)]));
    expect(screen.getByText(/Para dar de alta el cliente me falta saber/)).toBeInTheDocument();
  });

  it("ERROR: an unknown `work_kind` falls back to the generic title, never to the identifier", () => {
    renderTimeline(build("run-a", [f.intakeMissing(1, "teleport_client")]));
    expect(screen.getByText("Me falta saber")).toBeInTheDocument();
    expect(screen.queryByText(/teleport_client/)).not.toBeInTheDocument();
  });

  it("is still chips and still not a form", () => {
    renderTimeline(build("run-a", [f.intakeCreateClient(1)]));
    expect(document.querySelector("form")).toBeNull();
    // One button per slot: they are answered in the composer, in any
    // order, in the user's own words.
    expect(screen.getAllByRole("button", { name: /^Responder/ })).toHaveLength(5);
  });

  it("promotes `forbidden_behaviour` to the top even though the wire put it last", () => {
    renderTimeline(build("run-a", [f.intakeCreateClient(1)]));
    const chips = screen.getAllByRole("button", { name: /^Responder/ });
    expect(chips[0]).toHaveAccessibleName(/Qué NO debe hacer el agente/);
  });

  it("gives it a badge of its own, so the tone is not the only carrier (WCAG 1.4.1)", () => {
    renderTimeline(build("run-a", [f.intakeCreateClient(1)]));
    expect(screen.getByText("evita incidentes")).toBeInTheDocument();
  });

  it("shows OUR reasoning for it, not the backend's one-liner", () => {
    renderTimeline(build("run-a", [f.intakeCreateClient(1)]));
    expect(screen.getByText(/evita la llamada del cliente enfadado/)).toBeInTheDocument();
  });

  it("PARTIAL: a slot with no `why` and no examples still renders its chip", () => {
    renderTimeline(
      build("run-a", [
        f.ev(1, "intake.missing", {
          work_kind: "publish",
          slots: [{ key: "ai_disclosure_decision", label: "Revelación", why: "", examples: [], required: true }],
        }),
      ]),
    );
    expect(screen.getByRole("button", { name: /Si el agente dice que es una IA/ })).toBeInTheDocument();
  });

  it("EN renders too", () => {
    renderTimeline(build("run-a", [f.intakeCreateClient(1)]), "en");
    expect(screen.getByText(/To set the client up I still need to know/)).toBeInTheDocument();
  });
});

// ── §4 · the ticket ────────────────────────────────────────────────────

function renderConfirm(state: CompanionState, locale: "es" | "en" = "es") {
  const item = state.items.find((i) => i.kind === "action");
  if (item?.kind !== "action") throw new Error("no action in state");
  const onDecide = vi.fn();
  render(
    <LocaleProvider locale={locale}>
      <ConfirmCard item={item} currentUserId="user_a_ab12cd34" busy={false} failure={null} onDecide={onDecide} />
    </LocaleProvider>,
  );
  return { onDecide, item };
}

describe("support proposal — the file, not a vague complaint (v2 §4.2)", () => {
  it("lists what the Companion already read, as a list and not as JSON", () => {
    renderConfirm(build("run-a", [f.hitlSupportRequested(1, "act-1")]));
    expect(screen.getByText("Ya comprobado")).toBeInTheDocument();
    expect(screen.getByText(/Catálogo de conectores \(14 disponibles, sin Shopify\)/)).toBeInTheDocument();
    // The generic key/value preview would have stringified the array.
    expect(document.body.textContent).not.toContain('["Catálogo');
  });

  it("paints `topic` as the slug it is, under a label — never as prose", () => {
    renderConfirm(build("run-a", [f.hitlSupportRequested(1, "act-1")]));
    expect(screen.getAllByText("Tema").length).toBeGreaterThan(0);
    expect(screen.getAllByText("connector.shopify").length).toBeGreaterThan(0);
  });

  it("labels a bridge AND says it does not replace the ticket (§25.4)", () => {
    renderConfirm(build("run-a", [f.hitlSupportRequested(1, "act-1", "support_help", true)]));
    expect(screen.getByText("Solución puente")).toBeInTheDocument();
    expect(screen.getByText(/abrimos el ticket igualmente/)).toBeInTheDocument();
  });

  it("names a capability request as such, not as an incident", () => {
    renderConfirm(build("run-a", [f.hitlSupportRequested(1, "act-1", "support_capability")]));
    expect(screen.getAllByText("Petición de funcionalidad").length).toBeGreaterThan(0);
  });
});

describe("ticket reference — the thing you repeat over the phone (v2 §4.4)", () => {
  function withTicket(sla = "business_hours") {
    let s = build("run-a", [f.hitlSupportRequested(1, "act-1")]);
    s = build("run-a", [f.supportTicket(2, "act-1", "AU-142", "help", sla)], s);
    return s;
  }

  it("shows the reference and translates the sla into a sentence", () => {
    renderConfirm(withTicket());
    expect(screen.getByText("AU-142")).toBeInTheDocument();
    expect(screen.getByText("Te respondemos en horario laboral.")).toBeInTheDocument();
    // The backend does not emit the sentence (§4.4), only the identifier.
    expect(document.body.textContent).not.toContain("business_hours");
  });

  it("makes it copyable, and confirms in a live region the modal cannot swallow", async () => {
    const user = userEvent.setup();
    // Spied, not replaced: after `setup()` user-event has installed its
    // own clipboard behind a getter-only property, so assigning over it
    // throws. Spying on its `writeText` observes the real call path.
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    renderConfirm(withTicket());
    await user.click(screen.getByRole("button", { name: "Copiar la referencia del ticket" }));
    expect(writeText).toHaveBeenCalledWith("AU-142");
    // The Toaster lives outside this dialog's inert region, so a screen
    // reader would never hear it — hence the region inside the card.
    const live = document.querySelector('[aria-live="polite"][role="status"]');
    expect(live?.textContent).toContain("AU-142");
  });

  it("translates the other two sla values too", () => {
    renderConfirm(withTicket("best_effort"));
    expect(screen.getByText(/Sin plazo comprometido/)).toBeInTheDocument();
  });

  it("does not survive a copy failure as a broken card", async () => {
    const user = userEvent.setup();
    // Denied permission or an insecure context: the reference is on
    // screen and selectable, so the feature degrades and does not break.
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    renderConfirm(withTicket());
    await user.click(screen.getByRole("button", { name: "Copiar la referencia del ticket" }));
    expect(screen.getByText("AU-142")).toBeInTheDocument();
    // And no "copied" announcement, because nothing was copied.
    const live = document.querySelector('[aria-live="polite"][role="status"]');
    expect(live?.textContent).toBe("");
  });
});

// ── §7.1 · publishing without a trial ──────────────────────────────────

describe("publishing without a trial warns — it does NOT block (v2 §7.1)", () => {
  it("shows the warning and leaves Confirm enabled", async () => {
    const user = userEvent.setup();
    const { onDecide } = renderConfirm(build("run-a", [f.hitlPublishRequested(1, "act-1", "not_tried")]));
    expect(screen.getByText("Vas a publicar sin probarlo")).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Confirmar" });
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    // Forbidding it would turn the trial into a toll people learn to
    // route around, so the click has to go through.
    expect(onDecide).toHaveBeenCalledWith("confirm");
  });

  it("says so differently when the trial ran and failed", () => {
    renderConfirm(build("run-a", [f.hitlPublishRequested(1, "act-1", "trial_failed")]));
    expect(screen.getByText("La prueba no pasó")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeEnabled();
  });

  it("says nothing when there is nothing to warn about", () => {
    renderConfirm(build("run-a", [f.hitlPublishRequested(1, "act-1", null)]));
    expect(screen.queryByText(/sin probarlo/)).not.toBeInTheDocument();
    expect(screen.queryByText(/La prueba no pasó/)).not.toBeInTheDocument();
  });
});

// ── §7 · the trial panel ───────────────────────────────────────────────

describe("trial panel — the three states of `trial` (v2 §7)", () => {
  it("EMPTY: `trial: null` paints nothing — this action admits no trial", () => {
    renderTimeline(build("run-a", [f.verifyResult(1, "act-1", true, null)]));
    expect(screen.queryByText(/playground/i)).not.toBeInTheDocument();
    expect(screen.queryByText("No lo probé")).not.toBeInTheDocument();
  });

  it("PARTIAL: `{ran:false}` IS the notice — the case `null` must not swallow", () => {
    renderTimeline(build("run-a", [f.verifyResult(1, "act-1", true, f.trialNotRun())]));
    expect(screen.getByText("No lo probé")).toBeInTheDocument();
  });

  it("IDEAL: turns, probes and named assertions", () => {
    renderTimeline(build("run-a", [f.verifyResult(1, "act-1", true, f.trialRan(true))]));
    expect(screen.getByText("¿Cuánto cuesta el bótox?")).toBeInTheDocument();
    // `checks[].name` is a stable English identifier we translate.
    expect(screen.getByText("No dio un precio")).toBeInTheDocument();
    expect(screen.queryByText("no_price_quoted")).not.toBeInTheDocument();
  });

  it("ERROR: a failed trial is red and does not blame the user", () => {
    renderTimeline(build("run-a", [f.verifyResult(1, "act-1", false, f.trialRan(false))]));
    expect(screen.getByText("La prueba falló")).toBeInTheDocument();
    expect(screen.getByText(/o me equivoqué yo, o el cambio no se aplicó/)).toBeInTheDocument();
  });

  it("says out loud that it does not hold the conversation", () => {
    render(
      <LocaleProvider locale="es">
        <TrialPanel trial={readTrial(f.trialRan(true))!} clientRef="boreal" />
      </LocaleProvider>,
    );
    expect(screen.getByText(/Aquí no está lo que respondió el agente/)).toBeInTheDocument();
  });

  it("links into the playground thread when the client can be recovered", () => {
    let s = build("run-a", [f.hitlSupportRequested(1, "act-1")]);
    s = build("run-a", [f.verifyResult(2, "act-1", true, f.trialRan())], s);
    expect(trialClientRef(s, "act-1")).toBe("boreal");
    render(
      <LocaleProvider locale="es">
        <TrialPanel trial={readTrial(f.trialRan(true))!} clientRef="boreal" />
      </LocaleProvider>,
    );
    const link = screen.getByRole("link", { name: /Abrir el hilo de playground/ });
    expect(link).toHaveAttribute("href", "/clients/boreal/playground?thread=4d2b");
  });

  it("shows the thread id instead of a dead link when the client is unknown", () => {
    // `verify.result` carries no `client_ref`, so this is reachable in
    // production whenever the preview does not name one. A link that goes
    // nowhere is worse than no link.
    render(
      <LocaleProvider locale="es">
        <TrialPanel trial={readTrial(f.trialRan(true))!} clientRef={null} />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("4d2b")).toBeInTheDocument();
  });

  it("uses a real table with row headers for the assertions", () => {
    render(
      <LocaleProvider locale="es">
        <TrialPanel trial={readTrial(f.trialRan(true))!} clientRef="boreal" />
      </LocaleProvider>,
    );
    const table = screen.getByRole("table");
    expect(within(table).getByRole("rowheader", { name: "No dio un precio" })).toBeInTheDocument();
  });

  it("does not encode pass/fail in colour alone", () => {
    render(
      <LocaleProvider locale="es">
        <TrialPanel trial={readTrial(f.trialRan(false))!} clientRef="boreal" />
      </LocaleProvider>,
    );
    expect(screen.getByText(/el turno falló/)).toBeInTheDocument();
  });
});

// ── §6 · the pause, in the composer ────────────────────────────────────

function renderComposer(overrides: Partial<React.ComponentProps<typeof Composer>> = {}) {
  const props: React.ComponentProps<typeof Composer> = {
    value: "hola",
    mode: "consult",
    busy: false,
    blocked: false,
    paused: null,
    exhausted: false,
    onChange: vi.fn(),
    onSend: vi.fn(),
    onStop: vi.fn(),
    onMode: vi.fn(),
    ...overrides,
  };
  render(
    <LocaleProvider locale="es">
      <Composer {...props} />
    </LocaleProvider>,
  );
  return props;
}

describe("the composer under a pause (v2 §6.5)", () => {
  const pause = { used: 2000000, cap: 2000000, period: "2026-08", resetsAt: "2026-09-01T00:00:00Z", scope: "partner" };

  it("IDEAL: no pause, the box works", () => {
    renderComposer();
    expect(screen.getByLabelText("Mensaje al Companion")).toBeEnabled();
    expect(screen.queryByText("En pausa")).not.toBeInTheDocument();
  });

  it("disables the box and says WHY and WHAT unblocks it", () => {
    renderComposer({ paused: pause });
    expect(screen.getByLabelText("Mensaje al Companion")).toBeDisabled();
    expect(screen.getByText("En pausa")).toBeInTheDocument();
    expect(screen.getByText(/Se reanuda subiendo el tope/)).toBeInTheDocument();
    // A disabled control with no way out is a wall.
    expect(screen.getByText(/no hace falta que reintentes/)).toBeInTheDocument();
  });

  it("shows the figures from the snapshot, so no second request is needed", () => {
    renderComposer({ paused: pause });
    expect(screen.getByText(/2.000.000 de 2.000.000/)).toBeInTheDocument();
  });

  it("says the conversation and a pending confirmation are both kept", () => {
    renderComposer({ paused: pause });
    expect(screen.getByText(/puedes responderla igual/)).toBeInTheDocument();
  });

  it("announces politely — `assertive` belongs to `hitl.requested` alone (§14)", () => {
    renderComposer({ paused: pause });
    const region = document.querySelector('[role="status"][aria-live="polite"]');
    expect(region?.textContent).toContain("En pausa");
    expect(document.querySelector('[aria-live="assertive"]')).toBeNull();
  });

  it("PARTIAL: `exhausted` with no snapshot gives the same state, fewer specifics", () => {
    renderComposer({ exhausted: true });
    expect(screen.getByLabelText("Mensaje al Companion")).toBeDisabled();
    expect(screen.getByText("En pausa")).toBeInTheDocument();
    expect(screen.getByText(/Se alcanzó el tope de tokens/)).toBeInTheDocument();
  });

  it("EN renders too", () => {
    render(
      <LocaleProvider locale="en">
        <Composer
          value=""
          mode="consult"
          busy={false}
          blocked={false}
          paused={pause}
          exhausted={false}
          onChange={vi.fn()}
          onSend={vi.fn()}
          onStop={vi.fn()}
          onMode={vi.fn()}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText("Paused")).toBeInTheDocument();
  });
});
