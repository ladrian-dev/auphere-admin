import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { SeedTemplate } from "@/lib/backend/onboarding";

import { TemplatePicker } from "../template-picker";

/**
 * A qué se dedica el negocio (spec 019, R2).
 *
 * Lo que estos tests fijan es la decisión que más pesa del alta: **nada viene
 * preseleccionado**. Hoy viene marcada la plantilla que la API devuelve
 * primera —por orden alfabético, no por encaje— y da la casualidad de que es
 * la más pesada de las trece. Un partner que da de alta una barbería aterriza
 * en un formulario de medicina estética.
 *
 * Una elección arbitraria es peor que ninguna: continuar por inercia con una
 * plantilla que nadie eligió es exactamente el defecto que esto corrige.
 */

function tpl(name: string, display: string, tools = 10): SeedTemplate {
  return { name, display_name: display, version: "1", vertical: name.replace(/_v\d+$/, ""), tools_count: tools, placeholders: [] };
}

const TRECE: SeedTemplate[] = [
  tpl("barbershop_v1", "Barbería / Peluquería", 18),
  tpl("restaurante_v1", "Restaurante (reservas)", 13),
  tpl("dental_v1", "Clínica dental", 14),
];

function mount(over: Partial<React.ComponentProps<typeof TemplatePicker>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <LocaleProvider locale="es">
      <TemplatePicker templates={TRECE} value={over.value ?? null} onChange={over.onChange ?? onChange} {...over} />
    </LocaleProvider>,
  );
  return { ...utils, onChange: over.onChange ?? onChange };
}

describe("Elegir plantilla · nada viene marcado", () => {
  it("sin elección previa, ningún botón está seleccionado", () => {
    mount();
    const opciones = screen.getAllByRole("radio");
    expect(opciones.length).toBeGreaterThan(0);
    expect(opciones.every((o) => o.getAttribute("aria-checked") === "false")).toBe(true);
  });

  it("elegir avisa a quien la usa, con el nombre interno de la plantilla", () => {
    const onChange = vi.fn();
    mount({ onChange });
    screen.getByRole("radio", { name: /Barbería/ }).click();
    expect(onChange).toHaveBeenCalledWith("barbershop_v1");
  });
});

describe("Elegir plantilla · encontrar la tuya", () => {
  it("buscar reduce la lista y dice cuántas quedan", async () => {
    const user = userEvent.setup();
    mount();
    expect(screen.getByText("3 de 3")).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox"), "restaur");
    expect(screen.getByText("1 de 3")).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Barbería/ })).toBeNull();
  });

  it("si no encuentra nada lo dice, y ofrece la salida", async () => {
    const user = userEvent.setup();
    mount();
    await user.type(screen.getByRole("searchbox"), "ferretería");
    expect(screen.getByText(/Nada coincide/)).toBeInTheDocument();
    // «Sin plantilla» sigue alcanzable: no encontrarla no puede ser un
    // callejón sin salida.
    expect(screen.getByRole("radio", { name: /Ninguna de estas/ })).toBeInTheDocument();
  });
});

describe("Elegir plantilla · qué trae cada una", () => {
  it("dice para qué sirve y cuántas habilidades enciende, no su clave interna", () => {
    mount();
    const barberia = screen.getByRole("radio", { name: /Barbería/ });
    expect(within(barberia).getByText(/18 habilidades/)).toBeInTheDocument();
    // La clave interna existe pero no compite con el nombre del negocio.
    expect(barberia.textContent).not.toContain("barbershop_v1");
  });

  it("empezar sin plantilla es una opción con nombre, y dice qué implica", () => {
    mount();
    const ninguna = screen.getByRole("radio", { name: /Ninguna de estas/ });
    expect(within(ninguna).getByText(/nace vacío/)).toBeInTheDocument();
  });

  it("«ninguna» se elige como cualquier otra", () => {
    const onChange = vi.fn();
    mount({ onChange });
    screen.getByRole("radio", { name: /Ninguna de estas/ }).click();
    expect(onChange).toHaveBeenCalledWith(null);
  });
});

describe("Elegir plantilla · cuando el catálogo no llega", () => {
  it("lo dice, y deja crear el cliente sin plantilla", () => {
    mount({ templates: null });
    expect(screen.getByText(/No se pudo leer el catálogo/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Ninguna de estas/ })).toBeInTheDocument();
  });
});
