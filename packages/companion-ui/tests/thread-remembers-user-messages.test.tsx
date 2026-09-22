import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createFetchTransport } from "../src/transport";
import { useCompanion } from "../src/use-companion";
import * as f from "./fixtures";

/**
 * El hilo recuerda la conversación entera — spec 013, Requisito 1.
 *
 * Al reabrir un hilo, el timeline se reconstruía **solo con los eventos** de
 * cada run. Y el mensaje de la persona no es un evento: es una fila de
 * `companion.messages`. Así que lo que ella escribió aparecía mientras duraba
 * la sesión —como acción local— y **desaparecía al recargar**.
 *
 * El resultado no era estético. Sin la pregunta delante, la respuesta es
 * ininteligible: no hay forma de saber qué se pidió.
 *
 * El dato **ya se guardaba**; lo que faltaba era devolverlo. Desde la 013 el
 * resumen de run lleva su `prompt`, y aquí se comprueba que la pantalla lo
 * usa — en su sitio, que es **antes** de los eventos de ese run.
 */
type WireEvent = ReturnType<typeof f.ev>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const fetchMock = vi.fn();
const transport = createFetchTransport("/api/companion");

beforeEach(() => {
  window.localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function router(handlers: Array<[RegExp, () => Response]>) {
  return (url: string, init?: RequestInit) => {
    const key = `${(init?.method ?? "GET").toUpperCase()} ${url}`;
    for (const [re, fn] of handlers) if (re.test(key)) return Promise.resolve(fn());
    throw new Error(`unrouted ${key}`);
  };
}

const eventsOf = (runId: string, events: WireEvent[]) =>
  json({ run_id: runId, events, next_seq: events.length + 1, available_from: null });

/** El listado de runs **con** su prompt, que es lo que la 013 añade. */
const runsWithPrompts = (threadId: string, runs: Array<{ run_id: string; prompt: string | null; status?: string }>) => ({
  thread_id: threadId,
  runs: runs.map((r, i) => ({
    run_id: r.run_id,
    status: r.status ?? "completed",
    started_at: `2026-09-20T10:0${i}:00Z`,
    ended_at: (r.status ?? "completed") === "running" ? null : `2026-09-20T10:0${i}:30Z`,
    prompt: r.prompt,
  })),
});

describe("al reabrir un hilo, está la conversación entera (R1.1, R1.2)", () => {
  it("pinta lo que escribió la persona, y no solo lo que respondió el teammate", async () => {
    fetchMock.mockImplementation(
      router([
        [
          /GET \/api\/companion\/threads\/t1\/runs/,
          () =>
            json(
              runsWithPrompts("t1", [
                { run_id: "run-a", prompt: "analiza las ventas de agosto" },
                { run_id: "run-b", prompt: "y compáralas con julio" },
              ]),
            ),
        ],
        [/\/runs\/run-a\/events/, () => eventsOf("run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "subieron un 12 %"), f.runCompleted(3, "run-a")])],
        [/\/runs\/run-b\/events/, () => eventsOf("run-b", [f.runStarted(1, "run-b"), f.textDelta(2, "julio fue peor"), f.runCompleted(3, "run-b")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion(transport));
    await act(async () => {
      await result.current.openThread("t1");
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    const dichos = result.current.state.items
      .filter((i) => i.kind === "user")
      .map((i) => (i.kind === "user" ? i.text : ""));

    expect(dichos).toEqual(["analiza las ventas de agosto", "y compáralas con julio"]);
  });

  it("y los pone en su sitio: la pregunta antes de su respuesta", async () => {
    fetchMock.mockImplementation(
      router([
        [
          /GET \/api\/companion\/threads\/t2\/runs/,
          () => json(runsWithPrompts("t2", [{ run_id: "run-a", prompt: "la pregunta" }])),
        ],
        [/\/runs\/run-a\/events/, () => eventsOf("run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "la respuesta"), f.runCompleted(3, "run-a")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion(transport));
    await act(async () => {
      await result.current.openThread("t2");
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    const orden = result.current.state.items
      .filter((i) => i.kind === "user" || i.kind === "assistant")
      .map((i) => i.kind);

    expect(orden).toEqual(["user", "assistant"]);
  });

  it("con un turno EN MARCHA, la pregunta ya está (R1.4)", async () => {
    // Recargar a mitad de respuesta no puede tragarse lo que se acaba de
    // escribir: es el momento en que más duele perderlo.
    fetchMock.mockImplementation(
      router([
        [
          /GET \/api\/companion\/threads\/t3\/runs/,
          () => json(runsWithPrompts("t3", [{ run_id: "run-vivo", prompt: "lo que acabo de escribir", status: "running" }])),
        ],
        [/GET \/api\/companion\/runs\/run-vivo\/events/, () => eventsOf("run-vivo", [f.runStarted(1, "run-vivo")])],
        [/\/runs\/run-vivo\/stream/, () => new Response("", { status: 200, headers: { "content-type": "text/event-stream" } })],
      ]),
    );

    const { result } = renderHook(() => useCompanion(transport));
    await act(async () => {
      await result.current.openThread("t3");
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    expect(result.current.state.items.find((i) => i.kind === "user")).toMatchObject({
      text: "lo que acabo de escribir",
    });
  });

  it("un run sin prompt no inventa una burbuja vacía", async () => {
    // `null` es la anomalía —no hay fila de mensaje para ese run— y se trata
    // como texto ausente, no como cadena vacía: una burbuja en blanco diría
    // que alguien escribió algo y no escribió nada.
    fetchMock.mockImplementation(
      router([
        [/GET \/api\/companion\/threads\/t4\/runs/, () => json(runsWithPrompts("t4", [{ run_id: "run-a", prompt: null }]))],
        [/\/runs\/run-a\/events/, () => eventsOf("run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "hola"), f.runCompleted(3, "run-a")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion(transport));
    await act(async () => {
      await result.current.openThread("t4");
    });
    await waitFor(() => expect(result.current.status).toBe("ready"));

    expect(result.current.state.items.filter((i) => i.kind === "user")).toHaveLength(0);
  });
});
