/** Requisito 3.2 — el parser SSE del principal: trozos partidos, CRLF, `id`, varios eventos. */
import { describe, expect, it } from "vitest";

import { SseParser, parseBlock, readSse } from "../src/sse.js";

describe("SseParser", () => {
  it("cierra eventos completos y guarda el resto para el siguiente trozo", () => {
    const p = new SseParser();
    expect(p.push("id: 1\nevent: ping\ndata: {\"ts\": 1}\n\nid: 2\nevent: text.delta\ndata: {\"te")).toEqual([
      { seq: 1, event: "ping", data: { ts: 1 } },
    ]);
    expect(p.push("xt\": \"hola\"}\n\n")).toEqual([{ seq: 2, event: "text.delta", data: { text: "hola" } }]);
  });
  it("acepta CRLF y comentarios", () => {
    const p = new SseParser();
    expect(p.push(": keepalive\r\nid: 7\r\nevent: run.completed\r\ndata: {}\r\n\r\n")).toEqual([
      { seq: 7, event: "run.completed", data: {} },
    ]);
  });
  it("un bloque sin data no es un evento; un data que no es JSON se conserva como raw", () => {
    expect(parseBlock("event: x")).toBeNull();
    expect(parseBlock("data: hola")).toEqual({ seq: 0, event: "message", data: { raw: "hola" } });
  });
  it("readSse lee un cuerpo entero y termina en EOF", async () => {
    const enc = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(enc.encode("id: 1\nevent: a\ndata: {}\n\nid: 2\nevent: b\n"));
        c.enqueue(enc.encode("data: {}\n\n"));
        c.close();
      },
    });
    const seen: string[] = [];
    await readSse(body, (ev) => seen.push(`${ev.seq}:${ev.event}`));
    expect(seen).toEqual(["1:a", "2:b"]);
  });
});
