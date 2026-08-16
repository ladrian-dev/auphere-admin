import { describe, expect, it } from "vitest";

import { SseParser, parseBlock } from "../sse";

describe("SseParser", () => {
  it("parses id/event/data blocks and JSON payloads", () => {
    const p = new SseParser();
    const evs = p.push('id: 1\nevent: run.started\ndata: {"run_id":"r1"}\n\nid: 2\nevent: text.delta\ndata: {"text":"Ho"}\n\n');
    expect(evs).toEqual([
      { seq: 1, event: "run.started", data: { run_id: "r1" } },
      { seq: 2, event: "text.delta", data: { text: "Ho" } },
    ]);
  });
  it("buffers messages split across chunks and CRLF", () => {
    const p = new SseParser();
    expect(p.push("id: 3\r\nevent: text.de")).toEqual([]);
    expect(p.push('lta\r\ndata: {"text":"la"}\r\n\r\n')).toEqual([{ seq: 3, event: "text.delta", data: { text: "la" } }]);
  });
  it("keeps non-JSON data as raw and ignores comments / empty ids", () => {
    expect(parseBlock(": keep-alive\nevent: ping\ndata: nope")).toEqual({ seq: 0, event: "ping", data: { raw: "nope" } });
    expect(parseBlock(": only a comment")).toBeNull();
  });
});
