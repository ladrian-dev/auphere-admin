// @vitest-environment jsdom
/**
 * Requisito 10.2 — aprobar, rechazar y —cuando aplique— aprobar siempre, **con
 * el teclado**.
 *
 * No es sólo poder tabular hasta el botón: eso ya se podía. Es que quien decide
 * veinte veces al día pueda hacerlo sin soltar el teclado, y que los atajos no
 * pisen nada del sistema ni de la aplicación.
 *
 * Y el orden de tabulación importa: **aprobar primero, rechazar al final**. Con
 * rechazar el primero, una tabulación de más y un Intro por costumbre cancelan
 * el trabajo de un teammate.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { ARM_MS } from "@nexus/companion-ui";
import { CompanionLocaleProvider, ConfirmCard, ExecCard } from "@nexus/companion-ui";
import type { ActionItem } from "@nexus/companion-ui";

afterEach(cleanup);

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

async function armada() {
  await new Promise((r) => setTimeout(r, ARM_MS + 10));
}

function confirmCard(onDecide = vi.fn()) {
  render(
    <CompanionLocaleProvider locale="es">
      <ConfirmCard item={ITEM} currentUserId="u-1" busy={false} failure={null} onDecide={onDecide} />
    </CompanionLocaleProvider>,
  );
  return onDecide;
}

describe("las tres salidas se alcanzan con el teclado", () => {
  it("aprobar es lo primero que recibe el foco de las tres", async () => {
    const user = userEvent.setup();
    confirmCard();
    // Con rechazar el primero, una tabulación de más y un Intro por costumbre
    // cancelan el trabajo de un teammate.
    await user.tab();
    expect(document.activeElement).toHaveAccessibleName("Confirmar");
  });

  it("y las tres están en el orden en que se leen", async () => {
    const user = userEvent.setup();
    confirmCard();
    const nombres: string[] = [];
    for (let i = 0; i < 3; i++) {
      await user.tab();
      nombres.push(document.activeElement?.textContent ?? "");
    }
    expect(nombres).toEqual(["Confirmar", "Cambiar algo", "Cancelar"]);
  });

  it("aprobar con Intro decide, no hace falta el ratón", async () => {
    const user = userEvent.setup();
    const onDecide = confirmCard();
    await armada();
    await user.tab();
    await user.keyboard("{Enter}");
    expect(onDecide).toHaveBeenCalledWith("confirm");
  });

  it("rechazar con Intro también", async () => {
    const user = userEvent.setup();
    const onDecide = confirmCard();
    await armada();
    await user.tab();
    await user.tab();
    await user.tab();
    await user.keyboard("{Enter}");
    expect(onDecide).toHaveBeenCalledWith("cancel");
  });

  it("y el espacio hace lo mismo: es un botón, no un enlace", async () => {
    const user = userEvent.setup();
    const onDecide = confirmCard();
    await armada();
    await user.tab();
    await user.keyboard(" ");
    expect(onDecide).toHaveBeenCalledWith("confirm");
  });
});

describe("la tarjeta de ejecución añade «siempre», y también con teclado", () => {
  it("las cuatro salidas se alcanzan tabulando", () => {
    render(
      <CompanionLocaleProvider locale="es">
        <ExecCard
          item={{ ...ITEM, actionKind: "local_exec", preview: { executable: "make", argv: ["make", "test"] } }}
          busy={false}
          onDecide={vi.fn()}
          onPolicy={vi.fn()}
        />
      </CompanionLocaleProvider>,
    );
    const botones = screen.getAllByRole("button");
    // Ninguno queda fuera del orden de tabulación.
    for (const boton of botones) expect(boton).not.toHaveAttribute("tabindex", "-1");
  });
});
