/**
 * Requisito 3.2 — los streams del hilo, vistos desde el proceso principal.
 *
 * Una conexión por `stream_id`; los eventos llegan por `app:event` y el final
 * por `app:stream.end`. Cerrar una vista **no** cancela el run (eso es
 * `DELETE /runs/{id}`) y no emite un final que el renderer no pidió.
 */
import { describe, expect, it, vi } from "vitest";

import type { SseEvent } from "../src/sse.js";
import { StreamHub } from "../src/stream-hub.js";

function sink() {
  return { event: vi.fn(), end: vi.fn() };
}
const ev = (seq: number): SseEvent => ({ seq, event: "text.delta", data: { text: "x" } });
const tick = () => new Promise((r) => setTimeout(r, 0));

describe("StreamHub", () => {
  it("entrega los eventos con su stream_id y avisa del final", async () => {
    const s = sink();
    const hub = new StreamHub(async (_path, _signal, onEvent) => {
      onEvent(ev(1));
      onEvent(ev(2));
    }, s);
    const id = hub.start("/api/companion/runs/r/stream?since_seq=0");
    await tick();
    expect(s.event.mock.calls.map(([p]) => p.stream_id)).toEqual([id, id]);
    expect(s.end).toHaveBeenCalledWith({ stream_id: id, ok: true });
    expect(hub.size).toBe(0);
  });

  it("un fallo de conexión se dice, no se traga", async () => {
    const s = sink();
    const hub = new StreamHub(async () => {
      throw new Error("stream 502");
    }, s);
    const id = hub.start("/x");
    await tick();
    expect(s.end).toHaveBeenCalledWith({ stream_id: id, ok: false });
  });

  it("cerrar desde el renderer aborta y NO emite final ni más eventos", async () => {
    const s = sink();
    let abort: AbortSignal | null = null;
    const hub = new StreamHub(
      (_path, signal, onEvent) =>
        new Promise<void>((resolve) => {
          abort = signal;
          signal.addEventListener("abort", () => {
            onEvent(ev(9));
            resolve();
          });
        }),
      s,
    );
    const id = hub.start("/x");
    hub.close(id);
    await tick();
    expect(abort?.aborted).toBe(true);
    expect(s.end).not.toHaveBeenCalled();
    expect(s.event).not.toHaveBeenCalled();
    expect(hub.size).toBe(0);
  });

  it("cada stream tiene su identificador y `closeAll` los cierra todos", async () => {
    const s = sink();
    const hub = new StreamHub((_p, signal) => new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve())), s);
    const a = hub.start("/a");
    const b = hub.start("/b");
    expect(a).not.toBe(b);
    expect(hub.size).toBe(2);
    hub.closeAll();
    expect(hub.size).toBe(0);
  });
});
