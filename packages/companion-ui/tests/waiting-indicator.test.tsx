/**
 * Spec 010, Requisito 4.8 — el indicador de espera no parpadea.
 *
 * Un esqueleto que aparece y se va en doscientos milisegundos no informa: se
 * lee como un salto de la pantalla, y la gente lo interpreta como que algo va
 * mal. Por debajo del umbral en el que una persona siente que ha esperado, lo
 * honesto es no enseñar nada.
 *
 * Y cuando sí aparece, **dice qué está pasando**: un rectángulo gris sin texto
 * no distingue «cargando» de «roto».
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompanionLocaleProvider } from "../src/i18n";
import { Timeline } from "../src/components/timeline";
import { emptyCompanionState } from "../src/state";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

beforeEach(() => {
  vi.useFakeTimers();
});

function pintarCargando() {
  return render(
    <CompanionLocaleProvider locale="es">
      <Timeline
        state={emptyCompanionState}
        status="loading"
        errorDetail={null}
        partial={false}
        currentUserId={null}
        deciding={false}
        decisionFailure={null}
        suggestions={[]}
        onRetry={() => {}}
        onSuggestion={() => {}}
        onAnswerSlot={() => {}}
        onDecide={() => {}}
      />
    </CompanionLocaleProvider>,
  );
}

/** El indicador, si está, se encuentra por su nombre accesible. */
function indicador(): HTMLElement | null {
  return screen.queryByRole("status", { name: /cargando/i });
}

async function esperar(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("lo inmediato no se anuncia", () => {
  it("al montar no hay indicador todavía", () => {
    pintarCargando();
    expect(indicador()).toBeNull();
  });

  it("si la respuesta llega enseguida, nunca llegó a verse", async () => {
    pintarCargando();
    await esperar(200);
    expect(indicador()).toBeNull();
  });
});

describe("cuando la espera se nota, se dice", () => {
  it("pasado el umbral aparece, y dice qué se está haciendo", async () => {
    pintarCargando();
    await esperar(600);
    const visto = indicador();
    expect(visto).not.toBeNull();
    // El nombre accesible es una frase, no un rectángulo sin texto.
    expect(visto!.getAttribute("aria-label")).toMatch(/\w{4,}\s+\w+/);
  });

  it("y el registro se declara ocupado desde el primer momento", () => {
    // Que el esqueleto tarde en aparecer no puede dejar mudo al lector de
    // pantalla: `aria-busy` va en el registro y no espera al umbral.
    pintarCargando();
    expect(screen.getByRole("log")).toHaveAttribute("aria-busy", "true");
  });
});
