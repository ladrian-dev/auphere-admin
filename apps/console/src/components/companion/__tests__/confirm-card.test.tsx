import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { ConfirmCard } from "../confirm-card";
import type { ActionItem } from "../state";
import { companionReducer, emptyCompanionState } from "../state";
import * as f from "./fixtures";

function actionFrom(expiresAt: string): ActionItem {
  const s = companionReducer(emptyCompanionState, {
    type: "event",
    runId: "run-a",
    ev: f.hitlRequested(1, "9c1e", expiresAt),
    now: 1,
  });
  const item = s.items.find((i) => i.kind === "action");
  if (!item || item.kind !== "action") throw new Error("no action");
  return item;
}

const FUTURE = "2126-08-18T14:33:00Z";
const PAST = "2020-08-18T14:33:00Z";

function renderCard(item: ActionItem, overrides: Partial<React.ComponentProps<typeof ConfirmCard>> = {}) {
  const onDecide = vi.fn();
  render(
    <LocaleProvider locale="es">
      <ConfirmCard item={item} currentUserId="user_a_ab12cd34" busy={false} failure={null} onDecide={onDecide} {...overrides} />
    </LocaleProvider>,
  );
  return { onDecide };
}

describe("ConfirmCard — the pending decision", () => {
  it("shows the title, the diff, the impact and the three outcomes", () => {
    renderCard(actionFrom(FUTURE));
    expect(screen.getByText("Publicar la v8 del agente de Clínica Boreal")).toBeInTheDocument();
    expect(screen.getByText("Responde siempre en inglés.")).toBeInTheDocument();
    expect(screen.getByText("Responde en el idioma del cliente.")).toBeInTheDocument();
    expect(screen.getByText("Canales afectados")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cambiar algo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
  });

  it("is fully operable from the keyboard", async () => {
    const user = userEvent.setup();
    const { onDecide } = renderCard(actionFrom(FUTURE));
    await user.tab();
    // Tab order reaches Confirm; Enter activates it.
    expect(screen.getByRole("button", { name: "Confirmar" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onDecide).toHaveBeenCalledWith("confirm");
  });

  it("sends the note back with an edit so the model can adjust the plan", async () => {
    const user = userEvent.setup();
    const { onDecide } = renderCard(actionFrom(FUTURE));
    await user.click(screen.getByRole("button", { name: "Cambiar algo" }));
    const box = screen.getByLabelText("Qué quieres cambiar");
    expect(box).toHaveFocus();
    await user.type(box, "sin tocar el horario");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(onDecide).toHaveBeenCalledWith("edit", "sin tocar el horario");
  });

  it("cancels with no note rather than swallowing the decision", async () => {
    const user = userEvent.setup();
    const { onDecide } = renderCard(actionFrom(FUTURE));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onDecide).toHaveBeenCalledWith("cancel");
  });

  it("shows a countdown driven only by expires_at", () => {
    renderCard(actionFrom(FUTURE));
    expect(screen.getByText(/Caduca en/)).toBeInTheDocument();
  });
});

describe("ConfirmCard — expiry and drift", () => {
  it("removes the buttons once expires_at has passed", () => {
    renderCard(actionFrom(PAST));
    expect(screen.queryByRole("button", { name: "Confirmar" })).not.toBeInTheDocument();
    expect(screen.getByText("Se pasó el plazo")).toBeInTheDocument();
  });

  it("says 'you ran out of time' for 409 action_expired", () => {
    renderCard(actionFrom(FUTURE), { failure: { status: 409, code: "action_expired" } });
    expect(screen.getByText("Se pasó el plazo")).toBeInTheDocument();
  });

  it("says 'someone changed this' for 412 state_changed — a DIFFERENT sentence", () => {
    renderCard(actionFrom(FUTURE), { failure: { status: 412, code: "state_changed" } });
    expect(screen.getByText("Alguien cambió esto mientras decidías")).toBeInTheDocument();
    expect(screen.queryByText("Se pasó el plazo")).not.toBeInTheDocument();
  });

  it("disables the buttons while the decision is in flight", () => {
    renderCard(actionFrom(FUTURE), { busy: true });
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeDisabled();
  });
});

describe("ConfirmCard — resolved", () => {
  it("seals the card and names the decider without leaking an email", () => {
    let s = companionReducer(emptyCompanionState, { type: "event", runId: "run-a", ev: f.hitlRequested(1), now: 1 });
    s = companionReducer(s, { type: "event", runId: "run-b", ev: f.hitlResolved(1, "9c1e", "cancel"), now: 2 });
    const item = s.items.find((i) => i.kind === "action");
    renderCard(item as ActionItem);
    expect(screen.getByText("Cancelado por ti")).toBeInTheDocument();
    expect(screen.getByText(/Mejor sin tocar el horario/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirmar" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("@");
  });
});

describe("ConfirmCard — an unknown kind still renders (§3.4)", () => {
  it("falls back to a generic key/value preview so CO-04 can add a kind", () => {
    const item: ActionItem = {
      ...actionFrom(FUTURE),
      actionKind: "something_invented_later",
      diff: null,
      impact: [],
      preview: { client_ref: "boreal", unknown_field: "42", flag: true },
    };
    renderCard(item);
    expect(screen.getByText("Cambio propuesto")).toBeInTheDocument();
    expect(screen.getByText("Cliente")).toBeInTheDocument();
    // No translation for this key: the raw key beats a blank cell.
    expect(screen.getByText("unknown_field")).toBeInTheDocument();
    expect(screen.getByText("Sí")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeInTheDocument();
  });
});
