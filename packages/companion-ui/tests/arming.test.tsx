/**
 * Spec 010, Requisito 10.3 — una pulsación en el instante de aparecer no cuenta.
 *
 * La tarjeta de confirmación llega **en medio de un hilo que se escribe solo** y
 * empuja hacia abajo lo que había. Quien estuviera pulsando algo justo ahí
 * acabaría autorizando sin haber leído nada.
 *
 * Lo que **no** se hace, y por qué: no se desactiva el botón. Un control apagado
 * que se enciende solo parece roto y no dice por qué. Se ignora la respuesta,
 * que desde fuera se ve igual que no haber pulsado.
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ARM_MS, isArmed } from "../src/arming";
import { CompanionLocaleProvider as LocaleProvider } from "../src/i18n";
import { ConfirmCard } from "../src/components/confirm-card";
import type { ActionItem } from "../src/state";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
beforeEach(() => vi.useFakeTimers());

const ITEM: ActionItem = {
  kind: "action",
  id: "a-1",
  runId: "run-1",
  actionKind: "send",
  title: "Enviar el presupuesto a Boreal",
  preview: {},
  diff: null,
  impact: [],
  expiresAt: null,
  state: "pending",
  decision: null,
  by: null,
  at: null,
  note: null,
  ticket: null,
};

function pintar(onDecide = vi.fn()) {
  render(
    <LocaleProvider locale="es">
      <ConfirmCard item={ITEM} currentUserId="u-1" busy={false} failure={null} onDecide={onDecide} />
    </LocaleProvider>,
  );
  return onDecide;
}

describe("el umbral", () => {
  it("es el que usan los navegadores para los diálogos de permisos", () => {
    expect(ARM_MS).toBe(250);
  });

  it("antes no, después sí", () => {
    expect(isArmed(1000, 1000)).toBe(false);
    expect(isArmed(1000, 1000 + ARM_MS - 1)).toBe(false);
    expect(isArmed(1000, 1000 + ARM_MS)).toBe(true);
  });
});

describe("en la tarjeta", () => {
  it("una pulsación en el instante de aparecer no decide nada", () => {
    const onDecide = pintar();
    screen.getByRole("button", { name: /confirmar/i }).click();
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("rechazar tampoco: la protección va en las dos direcciones", () => {
    const onDecide = pintar();
    screen.getByRole("button", { name: /cancelar/i }).click();
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("pasado el umbral, decide con normalidad", () => {
    const onDecide = pintar();
    act(() => {
      vi.advanceTimersByTime(ARM_MS);
    });
    screen.getByRole("button", { name: /confirmar/i }).click();
    expect(onDecide).toHaveBeenCalledWith("confirm");
  });

  it("el botón nunca se pinta apagado: uno que se enciende solo parece roto", () => {
    pintar();
    expect(screen.getByRole("button", { name: /confirmar/i })).not.toBeDisabled();
  });
});
