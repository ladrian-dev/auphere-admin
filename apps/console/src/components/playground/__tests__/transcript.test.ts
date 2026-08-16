import { describe, expect, it } from "vitest";

import type { SseEvent } from "../sse";
import { type TranscriptState, emptyTranscript, transcriptReducer } from "../transcript";

const ev = (seq: number, event: string, data: Record<string, unknown> = {}): SseEvent => ({ seq, event, data });
const feed = (state: TranscriptState, runId: string, events: SseEvent[], now = 1000): TranscriptState =>
  events.reduce((s, e) => transcriptReducer(s, { type: "event", runId, ev: e, now: now + e.seq * 10 }), state);

describe("transcriptReducer", () => {
  it("builds a turn from prompt + stream: text, tools, blocks, tokens, latency", () => {
    let s = transcriptReducer(emptyTranscript, { type: "prompt", runId: "r1", prompt: "hola", now: 1000 });
    s = feed(s, "r1", [
      ev(1, "run.started", { run_id: "r1" }),
      ev(2, "tool.call.started", { tool_call_id: "c1", name: "book_appointment", args: {} }),
      ev(3, "audit.blocked", { tool_name: "book_appointment", blocked_reason: "dry_run" }),
      ev(4, "tool.call.completed", { tool_call_id: "c1", latency_ms: 12 }),
      ev(5, "text.delta", { text: "Hola" }),
      ev(6, "text.delta", { text: " socio" }),
      ev(7, "reasoning.delta", { text: "hmm" }),
      ev(8, "cost.updated", { input_tokens: 120, output_tokens: 30, model: "claude-sonnet-4-6" }),
      ev(0, "ping", { ts: 1 }),
      ev(9, "budget.updated", { used: 150, cap: 2000000, remaining: 1999850, percent: 0.01, exhausted: false, period: "2026-08", resets_at: "2026-09-01T00:00:00+00:00" }),
      ev(10, "run.completed", { status: "completed" }),
    ]);
    const turn = s.turns[0]!;
    expect(turn.status).toBe("completed");
    expect(turn.reply).toBe("Hola socio");
    expect(turn.reasoning).toBe("hmm");
    expect(turn.tools).toEqual([{ id: "c1", name: "book_appointment", status: "blocked", blockedReason: "dry_run", latencyMs: 12 }]);
    expect(turn.inputTokens).toBe(120);
    expect(turn.outputTokens).toBe(30);
    expect(turn.model).toBe("claude-sonnet-4-6");
    expect(turn.latencyMs).toBe(90); // (1000+100) - (1000+10)
    expect(turn.lastSeq).toBe(10);
    expect(s.budget?.used).toBe(150);
    expect(s.budget?.exhausted).toBe(false);
  });

  it("falls back to the UCM text, keeps cancelled/error/gap and ignores unknown runs", () => {
    let s = transcriptReducer(emptyTranscript, { type: "prompt", runId: "r1", prompt: "x", now: 0 });
    s = feed(s, "r1", [
      ev(1, "run.started"),
      ev(2, "ucm.final", { ucm: { fallback_text: "Desde UCM" } }),
      ev(3, "resume.gap", { reason: "buffer_overflow" }),
      ev(4, "run.completed", { status: "cancelled" }),
    ]);
    expect(s.turns[0]!.reply).toBe("Desde UCM");
    expect(s.turns[0]!.gap).toBe(true);
    expect(s.turns[0]!.status).toBe("cancelled");
    const same = transcriptReducer(s, { type: "event", runId: "nope", ev: ev(1, "text.delta", { text: "z" }), now: 0 });
    expect(same).toBe(s);
    const failed = transcriptReducer(
      transcriptReducer(emptyTranscript, { type: "prompt", runId: "r2", prompt: "y", now: 0 }),
      { type: "stream_failed", runId: "r2", now: 5, message: "boom" },
    );
    expect(failed.turns[0]).toMatchObject({ status: "error", error: "boom" });
    // A stream failure after completion does not overwrite the outcome.
    expect(transcriptReducer(s, { type: "stream_failed", runId: "r1", now: 9, message: "late" }).turns[0]!.status).toBe("cancelled");
  });

  it("does not duplicate a prompt for the same run and marks exhausted budgets", () => {
    let s = transcriptReducer(emptyTranscript, { type: "prompt", runId: "r1", prompt: "a", now: 0 });
    s = transcriptReducer(s, { type: "prompt", runId: "r1", prompt: "a", now: 0 });
    expect(s.turns).toHaveLength(1);
    s = feed(s, "r1", [ev(1, "budget.updated", { used: 150, cap: 100, remaining: 0, percent: 100, exhausted: true, period: "2026-08", resets_at: "" })]);
    expect(s.budget?.exhausted).toBe(true);
  });
});
