import type { PlaygroundBudget } from "@/lib/backend/playground";

import type { SseEvent } from "./sse";

/**
 * Transcript of a playground session — pure reducer over the SSE events
 * of `GET …/playground/threads/{id}/stream` (see `api/qa_streaming.py`).
 *
 * Lives ONLY in browser memory (decision C8: no transcript over REST under
 * `/console/*`). Latency is measured on the client between `run.started`
 * and `run.completed`; tokens come from `cost.updated` (units, never USD).
 */
export type ToolCallStatus = "running" | "done" | "blocked" | "error";
export type ToolCall = { id: string; name: string; status: ToolCallStatus; blockedReason?: string; latencyMs?: number };

export type TurnStatus = "pending" | "running" | "completed" | "cancelled" | "error";
export type Turn = {
  runId: string;
  prompt: string;
  reply: string;
  reasoning: string;
  tools: ToolCall[];
  inputTokens: number;
  outputTokens: number;
  model: string | null;
  startedAt: number | null;
  endedAt: number | null;
  latencyMs: number | null;
  status: TurnStatus;
  error: string | null;
  lastSeq: number;
  gap: boolean;
};

export type TranscriptState = { turns: Turn[]; budget: PlaygroundBudget | null };

export type TranscriptAction =
  | { type: "prompt"; runId: string; prompt: string; now: number }
  | { type: "event"; runId: string; ev: SseEvent; now: number }
  | { type: "stream_failed"; runId: string; now: number; message: string }
  | { type: "budget"; budget: PlaygroundBudget }
  | { type: "reset" };

export const emptyTranscript: TranscriptState = { turns: [], budget: null };

export function newTurn(runId: string, prompt: string): Turn {
  return {
    runId,
    prompt,
    reply: "",
    reasoning: "",
    tools: [],
    inputTokens: 0,
    outputTokens: 0,
    model: null,
    startedAt: null,
    endedAt: null,
    latencyMs: null,
    status: "pending",
    error: null,
    lastSeq: 0,
    gap: false,
  };
}

const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

export function transcriptReducer(state: TranscriptState, action: TranscriptAction): TranscriptState {
  switch (action.type) {
    case "reset":
      return { ...emptyTranscript, budget: state.budget };
    case "budget":
      return { ...state, budget: action.budget };
    case "prompt":
      if (state.turns.some((t) => t.runId === action.runId)) return state;
      return { ...state, turns: [...state.turns, newTurn(action.runId, action.prompt)] };
    case "stream_failed":
      return mapTurn(state, action.runId, (t) =>
        t.status === "completed" || t.status === "cancelled"
          ? t
          : { ...t, status: "error", error: action.message, endedAt: action.now, latencyMs: t.startedAt ? action.now - t.startedAt : null },
      );
    case "event":
      return applyEvent(state, action.runId, action.ev, action.now);
  }
}

function mapTurn(state: TranscriptState, runId: string, fn: (t: Turn) => Turn): TranscriptState {
  const idx = state.turns.findIndex((t) => t.runId === runId);
  if (idx === -1) return state;
  const next = fn(state.turns[idx]!);
  if (next === state.turns[idx]) return state;
  const turns = state.turns.slice();
  turns[idx] = next;
  return { ...state, turns };
}

function applyEvent(state: TranscriptState, runId: string, ev: SseEvent, now: number): TranscriptState {
  const d = ev.data;
  if (ev.event === "budget.updated") {
    const budget: PlaygroundBudget = {
      used: num(d.used),
      cap: num(d.cap),
      remaining: num(d.remaining),
      percent: num(d.percent),
      exhausted: d.exhausted === true,
      period: str(d.period) ?? "",
      resets_at: str(d.resets_at) ?? "",
    };
    return { ...state, budget };
  }
  if (ev.event === "ping") return state;

  return mapTurn(state, runId, (turn) => {
    const seq = ev.seq > 0 ? Math.max(turn.lastSeq, ev.seq) : turn.lastSeq;
    const t: Turn = { ...turn, lastSeq: seq };
    switch (ev.event) {
      case "run.started":
        return { ...t, status: "running", startedAt: t.startedAt ?? now };
      case "text.delta":
        return { ...t, status: t.status === "pending" ? "running" : t.status, reply: t.reply + (str(d.text) ?? "") };
      case "reasoning.delta":
        return { ...t, reasoning: t.reasoning + (str(d.text) ?? "") };
      case "cost.updated":
        return {
          ...t,
          inputTokens: t.inputTokens + num(d.input_tokens),
          outputTokens: t.outputTokens + num(d.output_tokens),
          model: str(d.model) ?? t.model,
        };
      case "tool.call.started": {
        const id = str(d.tool_call_id) ?? str(d.call_id) ?? `${t.tools.length + 1}`;
        const name = str(d.name) ?? str(d.tool) ?? str(d.tool_name) ?? "tool";
        if (t.tools.some((c) => c.id === id)) return t;
        return { ...t, tools: [...t.tools, { id, name, status: "running" }] };
      }
      case "tool.call.completed": {
        const id = str(d.tool_call_id) ?? str(d.call_id);
        const error = str(d.error);
        const latencyMs = typeof d.latency_ms === "number" ? d.latency_ms : undefined;
        let found = false;
        const tools = t.tools.map((c) => {
          if (c.id !== id) return c;
          found = true;
          if (c.status === "blocked") return { ...c, latencyMs };
          return { ...c, status: error ? ("error" as const) : ("done" as const), latencyMs };
        });
        if (!found) {
          tools.push({
            id: id ?? `${t.tools.length + 1}`,
            name: str(d.name) ?? str(d.tool) ?? "tool",
            status: error ? "error" : "done",
            latencyMs,
          });
        }
        return { ...t, tools };
      }
      case "audit.blocked": {
        const name = str(d.tool_name) ?? str(d.name) ?? str(d.tool) ?? "tool";
        const reason = str(d.blocked_reason) ?? "dry_run";
        // Mark the most recent running call with that name; else add one.
        let idx = -1;
        for (let i = t.tools.length - 1; i >= 0; i--) {
          if (t.tools[i]!.name === name && t.tools[i]!.status === "running") {
            idx = i;
            break;
          }
        }
        const tools = t.tools.slice();
        if (idx === -1) tools.push({ id: `blocked-${tools.length + 1}`, name, status: "blocked", blockedReason: reason });
        else tools[idx] = { ...tools[idx]!, status: "blocked", blockedReason: reason };
        return { ...t, tools };
      }
      case "ucm.final": {
        if (t.reply) return t;
        const ucm = d.ucm && typeof d.ucm === "object" ? (d.ucm as Record<string, unknown>) : null;
        const content = ucm?.content && typeof ucm.content === "object" ? (ucm.content as Record<string, unknown>) : null;
        const text = str(ucm?.fallback_text) ?? str(content?.text) ?? "";
        return text ? { ...t, reply: text } : t;
      }
      case "run.completed": {
        const status = str(d.status);
        const final: TurnStatus = status === "cancelled" ? "cancelled" : status === "error" ? "error" : "completed";
        const endedAt = now;
        return {
          ...t,
          status: final,
          error: str(d.error),
          endedAt,
          latencyMs: t.startedAt !== null ? Math.max(0, endedAt - t.startedAt) : null,
        };
      }
      case "resume.gap":
        return { ...t, gap: true };
      default:
        return t;
    }
  });
}

/** Turn-level summary the inspector renders. */
export function turnTotals(turns: Turn[]): { inputTokens: number; outputTokens: number } {
  return turns.reduce(
    (acc, t) => ({ inputTokens: acc.inputTokens + t.inputTokens, outputTokens: acc.outputTokens + t.outputTokens }),
    { inputTokens: 0, outputTokens: 0 },
  );
}
