import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { MissingCapability } from "@/lib/backend/builder-types";

const { MissingCapabilities } = await import("../missing-capabilities");

/**
 * Spec 047, enmienda del 2026-10-30 (T228; requisitos 65.3 y 65.4;
 * `contracts/console-api.md` §11) — «No tenemos herramienta para: …». Sale de
 * `missing_capabilities` con la `label` de cada elemento y dice la alternativa
 * del agente: pasar a una persona. Con la lista vacía no se enseña nada. Sus
 * cinco estados: cargando (esqueleto del tamaño de lo que había), vacío, error
 * (con «Reintentar», sin doble envío), parcial (sin `label`, por su clave) e
 * ideal.
 */

const FACTURAS: MissingCapability = {
  kind: "action",
  key: "invoice",
  label: "emitir facturas",
  reason: "no_tool",
  source: "text",
  pointer: "/procedures/0/steps",
};
const QUICKBOOKS: MissingCapability = { kind: "integration", key: "quickbooks", label: "quickbooks", reason: "integration_unknown", source: "skill", pointer: null };
const AGENDA: MissingCapability = {
  kind: "module",
  key: "reservas",
  label: "la agenda (Reservas no está activo para este cliente)",
  reason: "module_off",
  source: "connection_request",
  pointer: null,
};

function notice(props: Partial<React.ComponentProps<typeof MissingCapabilities>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <MissingCapabilities items={[QUICKBOOKS]} {...props} />
    </LocaleProvider>,
  );
}

describe("«No tenemos herramienta para: …» (65.3, 65.4)", () => {
  it("ideal, una: la frase con su `label` y la alternativa del agente; pasa axe", async () => {
    const { container } = notice();
    const box = container.querySelector("[data-slot=missing-capabilities]") as HTMLElement;
    expect(within(box).getByText("No tenemos herramienta para: quickbooks")).toBeVisible();
    expect(within(box).getByText("Si se lo piden, el agente pasa la conversación a una persona.")).toBeVisible();
    // Nada de esto se «conecta» (65.3).
    expect(within(box).queryByRole("button", { name: /Conectar/ })).toBeNull();
    expect(within(box).queryByRole("link")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("ideal, varias: una lista con la `label` de cada una; una promesa del texto lleva a su punto", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const { container } = notice({ items: [QUICKBOOKS, AGENDA, FACTURAS], canEdit: true, onEdit });
    const box = container.querySelector("[data-slot=missing-capabilities]") as HTMLElement;
    expect(within(box).getByText("No tenemos herramienta para:")).toBeVisible();
    const list = within(box).getByRole("list", { name: "No tenemos herramienta para:" });
    expect(within(list).getAllByRole("listitem").map((li) => li.querySelector("[data-slot=missing-label]")?.textContent)).toEqual([
      "quickbooks",
      "la agenda (Reservas no está activo para este cliente)",
      "emitir facturas",
    ]);
    const promise = within(list).getAllByRole("listitem")[2]!;
    expect(within(promise).getByText("Lo promete su texto.")).toBeVisible();
    // El nombre accesible empieza por lo que se ve (WCAG 2.5.3).
    const remove = within(promise).getByRole("button", { name: "Quitar la promesa: emitir facturas" });
    expect(remove).toHaveTextContent("Quitar la promesa");
    await user.click(remove);
    expect(onEdit).toHaveBeenCalledWith("/procedures/0/steps");
    expect(within(box).getByText("Si se lo piden, el agente pasa la conversación a una persona.")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("quien solo lee lo ve sin «Quitar la promesa» (§V)", () => {
    notice({ items: [FACTURAS], canEdit: false, onEdit: vi.fn() });
    expect(screen.getByText("No tenemos herramienta para: emitir facturas")).toBeVisible();
    expect(screen.getByText("Lo promete su texto.")).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("vacío: no se enseña nada", () => {
    const { container } = notice({ items: [] });
    expect(container.querySelector("[data-slot=missing-capabilities]")).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });

  it("parcial: una sin `label` se nombra por su clave", () => {
    notice({ items: [{ ...QUICKBOOKS, key: "mercadopago", label: "" }] });
    expect(screen.getByText("No tenemos herramienta para: Mercado Pago")).toBeVisible();
  });

  it("cargando: un esqueleto con el tamaño de lo que había, anunciado; sin nada antes, no salta nada", async () => {
    const { container, rerender } = notice({ items: [QUICKBOOKS, AGENDA], state: "loading" });
    const status = screen.getByRole("status", { name: "Comprobando qué herramientas faltan…" });
    // El título, una línea por cada una y la alternativa.
    expect(status.querySelectorAll("[data-slot=skeleton]").length).toBe(4);
    expect(screen.queryByText(/No tenemos herramienta/)).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
    rerender(
      <LocaleProvider locale="es">
        <MissingCapabilities items={[]} state="loading" />
      </LocaleProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("error: lo dice y «Reintentar» no se pulsa dos veces mientras vuelve a leer", async () => {
    const user = userEvent.setup();
    let release: () => void = () => undefined;
    const onRetry = vi.fn(() => new Promise<void>((resolve) => (release = resolve)));
    const { container } = notice({ items: [QUICKBOOKS], state: "failed", onRetry });
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos comprobar qué herramientas le faltan a este agente.");
    // Lo que había puede estar viejo: no se enseña como si fuera de ahora.
    expect(screen.queryByText(/No tenemos herramienta/)).toBeNull();
    const retry = screen.getByRole("button", { name: "Reintentar" });
    await user.click(retry);
    expect(retry).toBeDisabled();
    await user.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
    await act(async () => release());
    expect(retry).toBeEnabled();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("un texto largo no desborda: los elementos ceden su ancho (`min-w-0`)", () => {
    const long = "Rechnungen mit automatischer Umsatzsteuerberechnung ausstellen und versenden";
    const { container } = notice({ items: [{ ...FACTURAS, label: long }, QUICKBOOKS], canEdit: true, onEdit: vi.fn() });
    const label = within(container).getByText(long);
    expect(label.className).toMatch(/break-words/);
    for (const li of within(container).getAllByRole("listitem")) expect(li.className).toMatch(/min-w-0/);
  });
});
