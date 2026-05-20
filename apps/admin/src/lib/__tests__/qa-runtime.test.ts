/**
 * Unit tests for the qa-runtime SSE → ThreadMessage reducer
 * (ADR-021 Fase 2). The actual hook needs jsdom + EventSource so we
 * test the pure reducer + hydrator instead — easy, fast, deterministic.
 */
import { describe, expect, it } from "vitest";

import type { QAHistoryMessage } from "../qa-api";
import { __testing } from "../qa-runtime";
import type { QASSEEvent } from "../qa-sse";

const { applyEvent, hydrateMessage, assistantMessage } = __testing;

function blankAssistant() {
  return assistantMessage([], { type: "running" }, "asst-1");
}

function ev(event: QASSEEvent["event"], data: object): QASSEEvent {
  return { event, data } as QASSEEvent;
}

describe("qa-runtime — applyEvent", () => {
  it("appends text.delta into a single text part", () => {
    let msg = blankAssistant();
    msg = applyEvent(msg, ev("text.delta", { message_id: "m1", text: "Hola " }));
    msg = applyEvent(msg, ev("text.delta", { message_id: "m1", text: "Lee" }));
    expect(msg.content).toHaveLength(1);
    expect(msg.content[0]).toMatchObject({ type: "text", text: "Hola Lee" });
  });

  it("starts a new text part after a tool call", () => {
    let msg = blankAssistant();
    msg = applyEvent(msg, ev("text.delta", { text: "Voy a chequear..." }));
    msg = applyEvent(
      msg,
      ev("tool.call.started", {
        tool_call_id: "t1",
        name: "booking.check_availability",
        args: {},
      }),
    );
    msg = applyEvent(msg, ev("text.delta", { text: "Listo!" }));
    const types = msg.content.map((p) => p.type);
    expect(types).toEqual(["text", "tool-call", "text"]);
  });

  it("emits a reasoning part separately from text", () => {
    let msg = blankAssistant();
    msg = applyEvent(msg, ev("reasoning.delta", { text: "thinking..." }));
    msg = applyEvent(msg, ev("text.delta", { text: "Hola" }));
    const types = msg.content.map((p) => p.type);
    expect(types).toEqual(["reasoning", "text"]);
  });

  it("updates the same tool-call slot on completion", () => {
    let msg = blankAssistant();
    msg = applyEvent(
      msg,
      ev("tool.call.started", {
        tool_call_id: "t1",
        name: "booking.check_availability",
        args: { date: "tomorrow" },
      }),
    );
    msg = applyEvent(
      msg,
      ev("tool.call.completed", {
        tool_call_id: "t1",
        result: { slots: ["10:00"] },
        latency_ms: 200,
      }),
    );
    const calls = msg.content.filter((p) => p.type === "tool-call");
    expect(calls).toHaveLength(1);
    const tc = calls[0] as {
      toolCallId: string;
      toolName: string;
      result: { slots: string[] };
    };
    expect(tc.toolCallId).toBe("t1");
    expect(tc.toolName).toBe("booking.check_availability");
    expect(tc.result).toEqual({ slots: ["10:00"] });
  });

  it("appends a UCM data part on ucm.final", () => {
    let msg = blankAssistant();
    const ucm = { type: "text", content: { text: "Hola" } };
    msg = applyEvent(msg, ev("ucm.final", { message_id: "m1", ucm, intent: "info" }));
    expect(msg.content[0]).toMatchObject({
      type: "data",
      name: "ucm",
      data: ucm,
    });
  });

  it("appends an audit data part on audit.blocked", () => {
    let msg = blankAssistant();
    msg = applyEvent(
      msg,
      ev("audit.blocked", {
        tool_name: "booking.create_appointment",
        tool_args: { when: "tomorrow" },
        blocked_reason: "dry_run",
      }),
    );
    expect(msg.content[0]).toMatchObject({
      type: "data",
      name: "audit",
    });
  });

  it("accumulates cost.updated into metadata.steps", () => {
    let msg = blankAssistant();
    msg = applyEvent(
      msg,
      ev("cost.updated", { input_tokens: 50, output_tokens: 20 }),
    );
    msg = applyEvent(
      msg,
      ev("cost.updated", { input_tokens: 10, output_tokens: 5 }),
    );
    expect(msg.metadata.steps).toHaveLength(2);
    const totals = msg.metadata.steps.reduce(
      (acc, s) => {
        acc.input += s.usage?.inputTokens ?? 0;
        acc.output += s.usage?.outputTokens ?? 0;
        return acc;
      },
      { input: 0, output: 0 },
    );
    expect(totals).toEqual({ input: 60, output: 25 });
  });

  it("ignores lifecycle events (run.started / run.completed / ping)", () => {
    let msg = blankAssistant();
    msg = applyEvent(msg, ev("run.started", { run_id: "r1" }));
    msg = applyEvent(msg, ev("ping", { ts: Date.now() }));
    expect(msg.content).toHaveLength(0);
    expect(msg.metadata.steps).toHaveLength(0);
  });

  it("doesn't append empty text deltas", () => {
    let msg = blankAssistant();
    msg = applyEvent(msg, ev("text.delta", { message_id: "m1", text: "" }));
    expect(msg.content).toHaveLength(0);
  });
});

describe("qa-runtime — hydrateMessage", () => {
  it("turns an inbound row into a ThreadUserMessage", () => {
    const row: QAHistoryMessage = {
      id: "in-1",
      direction: "inbound",
      content: "hola",
      ucm: null,
      tool_calls: [],
      created_at: "2026-05-20T00:00:00Z",
    };
    const m = hydrateMessage(row);
    expect(m.role).toBe("user");
    if (m.role === "user") {
      expect(m.content).toEqual([{ type: "text", text: "hola" }]);
    }
  });

  it("turns an outbound row with content into a ThreadAssistantMessage with text", () => {
    const row: QAHistoryMessage = {
      id: "out-1",
      direction: "outbound",
      content: "Hola Lee",
      ucm: null,
      tool_calls: [],
      created_at: "2026-05-20T00:00:00Z",
    };
    const m = hydrateMessage(row);
    expect(m.role).toBe("assistant");
    if (m.role === "assistant") {
      expect(m.content[0]).toMatchObject({ type: "text", text: "Hola Lee" });
      expect(m.status).toEqual({ type: "complete", reason: "stop" });
    }
  });

  it("includes a UCM data part when persisted history carries one", () => {
    const ucm = { type: "text", content: { text: "Hola" } };
    const row: QAHistoryMessage = {
      id: "out-2",
      direction: "outbound",
      content: "Hola",
      ucm,
      tool_calls: [],
      created_at: "2026-05-20T00:00:00Z",
    };
    const m = hydrateMessage(row);
    if (m.role === "assistant") {
      const partTypes = m.content.map((p) => p.type);
      expect(partTypes).toContain("data");
    }
  });
});
