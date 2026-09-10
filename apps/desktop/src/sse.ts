/**
 * Parser SSE del proceso principal (spec 003, D9). Puro: se le dan trozos de
 * texto y devuelve eventos completos; aguanta mensajes partidos entre trozos
 * y CRLF. Es el gemelo del de `@nexus/companion-ui` — el principal corre en
 * Node y no puede importar un paquete de TypeScript sin compilar, así que el
 * parser vive aquí con su propio test.
 */
export type SseEvent = { seq: number; event: string; data: Record<string, unknown> };

export class SseParser {
  private buffer = "";

  push(chunk: string): SseEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const out: SseEvent[] = [];
    let idx: number;
    while ((idx = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2);
      const ev = parseBlock(block);
      if (ev) out.push(ev);
    }
    return out;
  }
}

export function parseBlock(block: string): SseEvent | null {
  let seq = 0;
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") seq = Number.parseInt(value, 10) || 0;
    else if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  let data: Record<string, unknown> = {};
  try {
    const parsed: unknown = JSON.parse(dataLines.join("\n"));
    if (parsed && typeof parsed === "object") data = parsed as Record<string, unknown>;
  } catch {
    data = { raw: dataLines.join("\n") };
  }
  return { seq, event, data };
}

/** Lee un cuerpo `ReadableStream` como SSE hasta el final. */
export async function readSse(
  body: ReadableStream<Uint8Array>,
  onEvent: (ev: SseEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const ev of parser.push(decoder.decode(value, { stream: true }))) onEvent(ev);
  }
}
