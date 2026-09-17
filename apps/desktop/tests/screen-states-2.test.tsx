// @vitest-environment jsdom
/**
 * Requisitos 4.1 y 4.9 — el inventario de estados, parte 2: el hilo, el
 * entorno, las notas de cambio, los ajustes del teammate y las secciones de
 * administrar.
 *
 * Las tres primeras ya tienen sus tests desde la spec 003 (`env-panel`,
 * `change-notes`, `teammate-settings`); lo que falta y se añade aquí es lo que
 * ninguno cubría:
 *
 * * **el hilo contra la tabla entera**, incluida la regla que costó un P0 —
 *   «vacío» solo cuando de verdad está vacío, nunca como disfraz de un fallo;
 * * **las secciones de administrar**, que las pinta la consola dentro del
 *   panel: cuando esa carga falla, lo que se veía era la página de error de
 *   Chromium dentro de la ventana, en inglés, sin nada que pulsar.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { THREAD_STATES, type ThreadFacts, deriveThreadState } from "../src/app-state";
import { SectionFailed } from "../src/app/routes/section-failed";

afterEach(cleanup);

/** Un hilo normal, del que se cambia un hecho cada vez. */
const NORMAL: ThreadFacts = {
  status: "ready",
  runStatus: "idle",
  reconnecting: false,
  partial: false,
  itemCount: 3,
  taskState: null,
  budgetPaused: false,
  machineNeeded: false,
  machinePresent: true,
};

describe("Hilo — cada celda de la tabla llega a verse", () => {
  const casos: Array<[string, Partial<ThreadFacts>]> = [
    ["cargando", { status: "loading" }],
    ["error", { status: "error" }],
    ["reconectando", { reconnecting: true }],
    ["parcial", { partial: true }],
    ["en_pausa_por_tope", { budgetPaused: true }],
    ["esperandote", { runStatus: "waiting" }],
    ["maquina_ausente", { machineNeeded: true, machinePresent: false }],
    ["vacio", { itemCount: 0 }],
    // R4.7. La tabla §5 no le da columna porque hoy no llega de la plataforma;
    // la tiene aquí para que no se cuele en `normal` el día que llegue.
    ["bloqueado", { blockedOn: "Nilo" }],
    ["normal", {}],
  ];

  for (const [esperado, hechos] of casos) {
    it(`${esperado} es alcanzable`, () => {
      expect(deriveThreadState({ ...NORMAL, ...hechos })).toBe(esperado);
    });
  }

  it("y ninguno de los diez se queda sin caso", () => {
    const vistos = new Set(casos.map(([nombre]) => nombre));
    for (const estado of THREAD_STATES) {
      expect(vistos.has(estado), `${estado} no tiene caso`).toBe(true);
    }
  });

  it("un hilo que falló al abrirse NO se llama vacío — el P0 de la tabla", () => {
    // `itemCount: 0` con `status: "error"` es exactamente el hilo que no se
    // pudo leer. Pintarlo como «tu hilo está vacío» era la mentira más barata
    // de la aplicación, porque parecía una pantalla bien resuelta.
    expect(deriveThreadState({ ...NORMAL, status: "error", itemCount: 0 })).toBe("error");
  });

  it("ni un hilo vacío que está reconectando", () => {
    expect(deriveThreadState({ ...NORMAL, reconnecting: true, itemCount: 0 })).toBe("reconectando");
  });
});

describe("Secciones de administrar — cuando la consola no carga", () => {
  it("se dice en la lengua de la aplicación, no con la página de Chromium", () => {
    render(<SectionFailed section="clientes" onRetry={() => {}} />);
    const dicho = screen.getByRole("status");
    expect(dicho).toHaveTextContent(/no se pudo cargar|could not be loaded/i);
    // Y se nombra **qué** sección: «no se pudo cargar» a secas no deja saber
    // si falló lo que pediste o la aplicación entera.
    expect(dicho).toHaveTextContent(/clientes|clients/i);
  });

  it("ofrece reintentar, que es la salida que la tabla exige", async () => {
    const onRetry = vi.fn();
    render(<SectionFailed section="clientes" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /reintentar|retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("no se pinta en rojo: una sección que no carga no es una avería tuya", () => {
    const { container } = render(<SectionFailed section="clientes" onRetry={() => {}} />);
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector(".text-status-danger")).toBeNull();
  });
});
