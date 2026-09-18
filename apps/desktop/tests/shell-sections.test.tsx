// @vitest-environment jsdom
/**
 * Requisitos 1.2 y 1.3 — **la lista lateral es sólo lo que se opera**.
 *
 * Este test decía lo contrario. Comprobaba que la lista espejara las **diez**
 * secciones de la consola, porque el análisis de la spec había encontrado que
 * la lista canónica tenía cinco y la consola ofrecía diez: al esconder la barra
 * de la consola dentro de la ventana, cinco áreas se quedaban sin camino.
 *
 * La enmienda del 2026-09-18 resuelve ese problema por la raíz en vez de por
 * paridad: **la consola ya no se esconde**. Entra entera, con su propia barra,
 * y por eso no hay nada que espejar ni que mantener sincronizado. Lo que se
 * miró funcionando antes de decidirlo: dos barras laterales, dos buscadores,
 * dos campanas y dos identidades en la misma ventana — y el glosario ya
 * divergiendo («Playbook» en una, «Conocimiento» en la otra).
 *
 * Lo que este test vigila ahora es que no vuelva: si alguien añade otra vez las
 * secciones de la consola a esta lista, se pone rojo.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { CONSOLE_SECTIONS } from "../src/sections";
import { Sidebar } from "../src/app/shell/sidebar";

afterEach(cleanup);

function pintar(over: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props: React.ComponentProps<typeof Sidebar> = {
    active: "hoy",
    onSelect: vi.fn(),
    waiting: 0,
    teammates: [{ id: "t-1", name: "Sofía", unread: false }],
    rosterStatus: "ready",
    selectedTeammate: null,
    onSelectTeammate: vi.fn(),
    ...over,
  };
  render(<Sidebar {...props} />);
  return props;
}

describe("la lista lateral no espeja la consola", () => {
  it("ni con todos los permisos aparece ninguna sección de administrar", () => {
    pintar();
    const lista = screen.getByRole("navigation");
    for (const seccion of CONSOLE_SECTIONS) {
      // «Inicio», «Clientes», «Facturación»… son de la consola y viven allí.
      expect(
        within(lista).queryByRole("button", { name: new RegExp(`^${etiqueta(seccion.key)}$`, "i") }),
        `«${seccion.key}» volvió a la lista lateral`,
      ).toBeNull();
    }
  });

  it("lo que sí está es lo que se opera, y nada más", () => {
    pintar();
    const lista = screen.getByRole("navigation");
    for (const nombre of [/hoy|today/i, /pendientes|pending/i, /Sofía/]) {
      expect(within(lista).getByRole("button", { name: nombre })).toBeInTheDocument();
    }
  });

  it("y la lista ya no recibe permisos: la consola decide los suyos", () => {
    // Recibía la lista de permisos de la persona para filtrar las secciones de
    // administrar. Era una segunda copia de las reglas de la consola que había
    // que mantener al día; ahora ni existe el argumento.
    const props = pintar();
    expect(props).not.toHaveProperty("permissions");
  });
});

describe("y la sección activa se sigue anunciando", () => {
  it("la actual es la página actual, y sólo una", () => {
    pintar({ active: "pendientes" });
    const actuales = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "page");
    expect(actuales).toHaveLength(1);
    expect(actuales[0]).toHaveAccessibleName(/pendientes|pending/i);
  });
});

describe("el teammate sigue llevando a su hilo", () => {
  it("un clic lo selecciona", async () => {
    const props = pintar();
    await userEvent.click(screen.getByRole("button", { name: /Sofía/ }));
    expect(props.onSelectTeammate).toHaveBeenCalledWith("t-1");
  });
});

/** El texto con el que la lista llamaba a cada sección de la consola. */
function etiqueta(key: string): string {
  const copia: Record<string, string> = {
    inicio: "Inicio",
    clientes: "Clientes",
    conocimiento: "Conocimiento",
    puesto: "Puesto de trabajo",
    consumo: "Consumo",
    auditoria: "Auditoría",
    notificaciones: "Notificaciones",
    equipo: "Equipo",
    claves: "Claves de API",
    facturacion: "Facturación",
  };
  return copia[key] ?? key;
}
