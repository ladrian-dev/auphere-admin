/**
 * Los streams abiertos por la pantalla — spec 003, D9.
 *
 * El renderer pide `app:stream.open` y recibe los eventos por `app:event`;
 * cuando la conexión termina o falla, `app:stream.end` dice cómo. El bucle
 * de reconexión vive en el renderer (`useCompanion`), como en la consola: aquí
 * solo hay una conexión por `stream_id`, y cerrar una vista nunca cancela el
 * run (eso es `DELETE /runs/{id}`).
 */
import type { SseEvent } from "./sse.js";

export type StreamSink = {
  event(payload: { stream_id: string; event: SseEvent }): void;
  end(payload: { stream_id: string; ok: boolean }): void;
};

export type StreamOpener = (path: string, signal: AbortSignal, onEvent: (ev: SseEvent) => void) => Promise<void>;

export class StreamHub {
  private readonly open = new Map<string, AbortController>();
  private seq = 0;

  constructor(
    private readonly opener: StreamOpener,
    private readonly sink: StreamSink,
  ) {}

  start(path: string): string {
    this.seq += 1;
    const streamId = `s${this.seq}`;
    const ac = new AbortController();
    this.open.set(streamId, ac);
    void this.opener(path, ac.signal, (event) => {
      if (!ac.signal.aborted) this.sink.event({ stream_id: streamId, event });
    })
      .then(() => this.finish(streamId, true))
      .catch(() => this.finish(streamId, !this.open.has(streamId) ? true : false));
    return streamId;
  }

  close(streamId: string): void {
    const ac = this.open.get(streamId);
    if (!ac) return;
    this.open.delete(streamId);
    ac.abort();
  }

  closeAll(): void {
    for (const id of [...this.open.keys()]) this.close(id);
  }

  get size(): number {
    return this.open.size;
  }

  private finish(streamId: string, ok: boolean): void {
    if (!this.open.has(streamId)) return; // cerrado por el renderer: sin aviso
    this.open.delete(streamId);
    this.sink.end({ stream_id: streamId, ok });
  }
}
