"use client";

import { Archive, MessageSquarePlus, Pencil, Send, Square } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Input,
  Textarea,
  formatRelative,
} from "@nexus/ui";

import {
  cancelRunAction,
  createThreadAction,
  getBudgetAction,
  patchThreadAction,
  startRunAction,
} from "@/app/(console)/clients/[ref]/playground/actions";
import { useLocale, useT } from "@/i18n/client";
import type { PlaygroundBudget, PlaygroundThread } from "@/lib/backend/playground";

import { BudgetBar } from "./budget-bar";
import { SseParser } from "./sse";
import { type TranscriptAction, type TranscriptState, emptyTranscript, transcriptReducer } from "./transcript";
import { TurnInspector } from "./turn-inspector";

/**
 * The playground (CP-16): threads of the calling member against this
 * client's agent, a live transcript (browser memory only — C8), a per-turn
 * inspector and the partner's monthly token cap. Own compact component
 * instead of `@assistant-ui/react`: the event protocol is ours, the token
 * lint is strict, and the surface is small.
 */
type Props = {
  refId: string;
  initialThreads: PlaygroundThread[];
  initialBudget: PlaygroundBudget | null;
  budgetFailed: boolean;
  agentReady: boolean;
};

type State = { byThread: Record<string, TranscriptState>; budget: PlaygroundBudget | null };
type Action = { threadId: string; action: TranscriptAction } | { type: "budget"; budget: PlaygroundBudget | null };

function reducer(state: State, a: Action): State {
  if ("type" in a) return { ...state, budget: a.budget };
  const prev = state.byThread[a.threadId] ?? { ...emptyTranscript, budget: state.budget };
  const next = transcriptReducer(prev, a.action);
  if (next === prev) return state;
  return {
    byThread: { ...state.byThread, [a.threadId]: next },
    budget: a.action.type === "event" && a.action.ev.event === "budget.updated" ? next.budget : state.budget,
  };
}

const MAX_PROMPT = 4000;
const MAX_RECONNECTS = 3;

export function Playground({ refId, initialThreads, initialBudget, budgetFailed, agentReady }: Props) {
  const t = useT();
  const locale = useLocale();
  const [threads, setThreads] = React.useState<PlaygroundThread[]>(initialThreads);
  const [selectedId, setSelectedId] = React.useState<string | null>(initialThreads[0]?.id ?? null);
  const [state, dispatch] = React.useReducer(reducer, { byThread: {}, budget: initialBudget });
  const [budgetError, setBudgetError] = React.useState(budgetFailed);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [activeRun, setActiveRun] = React.useState<string | null>(null);
  const [reconnecting, setReconnecting] = React.useState(false);
  const [renaming, setRenaming] = React.useState<{ id: string; title: string } | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const bottomRef = React.useRef<HTMLDivElement | null>(null);
  const composerRef = React.useRef<HTMLTextAreaElement | null>(null);

  const transcript = selectedId ? (state.byThread[selectedId] ?? emptyTranscript) : emptyTranscript;
  const turns = transcript.turns;
  const lastTurn = turns[turns.length - 1] ?? null;
  const budget = state.budget;
  const exhausted = budget?.exhausted === true;
  const running = activeRun !== null;
  const canSend = !!selectedId && agentReady && !exhausted && !running && !busy;

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  const refreshBudget = React.useCallback(async () => {
    const res = await getBudgetAction();
    if (res.ok) {
      dispatch({ type: "budget", budget: res.data });
      setBudgetError(false);
    } else setBudgetError(true);
  }, []);

  async function createThread() {
    setBusy(true);
    const res = await createThreadAction({ ref: refId });
    setBusy(false);
    if (!res.ok) return void toast.error(res.message);
    setThreads((prev) => [res.data, ...prev]);
    setSelectedId(res.data.id);
    toast.success(t("playground.threads.created"));
    composerRef.current?.focus();
  }

  async function saveRename() {
    if (!renaming) return;
    const title = renaming.title.trim();
    const id = renaming.id;
    setRenaming(null);
    if (!title) return;
    const res = await patchThreadAction({ ref: refId, thread_id: id, title });
    if (!res.ok) return void toast.error(res.message);
    setThreads((prev) => prev.map((th) => (th.id === id ? res.data : th)));
  }

  async function archive(id: string) {
    const res = await patchThreadAction({ ref: refId, thread_id: id, archived: true });
    if (!res.ok) return void toast.error(res.message);
    setThreads((prev) => {
      const next = prev.filter((th) => th.id !== id);
      if (selectedId === id) setSelectedId(next[0]?.id ?? null);
      return next;
    });
    toast.success(t("playground.threads.archived"));
  }

  async function streamRun(threadId: string, runId: string) {
    const ac = new AbortController();
    abortRef.current = ac;
    let since = 0;
    let attempts = 0;
    let done = false;
    while (!done && !ac.signal.aborted) {
      try {
        const q = new URLSearchParams({ run_id: runId, since_seq: String(since) });
        const resp = await fetch(`/api/playground/${encodeURIComponent(refId)}/threads/${threadId}/stream?${q}`, {
          headers: { Accept: "text/event-stream" },
          signal: ac.signal,
          cache: "no-store",
        });
        if (!resp.ok || !resp.body) throw new Error(`stream ${resp.status}`);
        setReconnecting(false);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        const parser = new SseParser();
        for (;;) {
          const { value, done: eof } = await reader.read();
          if (eof) break;
          for (const ev of parser.push(decoder.decode(value, { stream: true }))) {
            if (ev.seq > since) since = ev.seq;
            dispatch({ threadId, action: { type: "event", runId, ev, now: Date.now() } });
            if (ev.event === "run.completed") done = true;
          }
          if (done) break;
        }
      } catch (err) {
        if (ac.signal.aborted) break;
        if (process.env.NODE_ENV !== "production") console.warn("playground stream", err);
      }
      if (done) break;
      attempts += 1;
      if (attempts > MAX_RECONNECTS) {
        dispatch({ threadId, action: { type: "stream_failed", runId, now: Date.now(), message: t("playground.run.error") } });
        break;
      }
      setReconnecting(true);
      await new Promise((r) => setTimeout(r, 400 * attempts));
    }
    setReconnecting(false);
    if (abortRef.current === ac) abortRef.current = null;
  }

  async function send() {
    if (!selectedId) return;
    const prompt = text.trim();
    if (!prompt || prompt.length > MAX_PROMPT) return;
    const threadId = selectedId;
    setBusy(true);
    const res = await startRunAction({ ref: refId, thread_id: threadId, prompt });
    setBusy(false);
    if (!res.ok) {
      if (res.status === 429) {
        await refreshBudget();
        dispatch({ type: "budget", budget: budget ? { ...budget, exhausted: true, remaining: 0, percent: 100 } : null });
      }
      toast.error(res.message);
      return;
    }
    const runId = res.data.run_id;
    setText("");
    setActiveRun(runId);
    dispatch({ threadId, action: { type: "prompt", runId, prompt, now: Date.now() } });
    setThreads((prev) =>
      prev.map((th) => (th.id === threadId ? { ...th, turn_count: th.turn_count + 1, last_run_at: new Date().toISOString() } : th)),
    );
    await streamRun(threadId, runId);
    setActiveRun(null);
    composerRef.current?.focus();
  }

  async function stop() {
    if (!activeRun) return;
    const res = await cancelRunAction({ ref: refId, run_id: activeRun });
    if (!res.ok) toast.error(res.message);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (canSend) void send();
    }
  }

  const selected = threads.find((th) => th.id === selectedId) ?? null;

  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <section className="flex min-w-0 flex-col gap-3" aria-label={t("playground.title")}>
        {/* threads */}
        <div className="flex min-w-0 items-center gap-2">
          <ul className="flex min-w-0 flex-1 gap-1 overflow-x-auto py-1" aria-label={t("playground.threads")}>
            {threads.map((th) => {
              const active = th.id === selectedId;
              const isRenaming = renaming?.id === th.id;
              return (
                <li key={th.id} className="flex shrink-0 items-center gap-1">
                  {isRenaming ? (
                    <Input
                      autoFocus
                      value={renaming.title}
                      aria-label={t("playground.threads.title.label")}
                      maxLength={200}
                      className="h-7 w-48 text-xs"
                      onChange={(e) => setRenaming({ id: th.id, title: e.target.value })}
                      onBlur={() => void saveRename()}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void saveRename();
                        }
                        if (e.key === "Escape") setRenaming(null);
                      }}
                    />
                  ) : (
                    <button
                      type="button"
                      onClick={() => setSelectedId(th.id)}
                      aria-pressed={active}
                      title={th.title}
                      className={[
                        "flex h-7 max-w-56 items-center gap-2 rounded-full border px-3 text-xs transition-colors",
                        active ? "border-foreground bg-foreground text-background" : "border-border text-muted-foreground hover:text-foreground",
                      ].join(" ")}
                    >
                      <span className="truncate">{th.title || t("playground.threads.untitled")}</span>
                      <span className="shrink-0 font-mono tabular-nums opacity-70">
                        {th.turn_count === 1 ? t("playground.threads.turn") : t("playground.threads.turns", { n: th.turn_count })}
                      </span>
                    </button>
                  )}
                  {active && !isRenaming ? (
                    <>
                      <Button variant="ghost" size="icon-xs" aria-label={t("playground.threads.rename")} onClick={() => setRenaming({ id: th.id, title: th.title })}>
                        <Pencil aria-hidden="true" />
                      </Button>
                      <Button variant="ghost" size="icon-xs" aria-label={t("playground.threads.archive")} disabled={running} onClick={() => void archive(th.id)}>
                        <Archive aria-hidden="true" />
                      </Button>
                    </>
                  ) : null}
                </li>
              );
            })}
          </ul>
          <Button size="sm" variant={threads.length ? "outline" : "default"} onClick={() => void createThread()} disabled={busy}>
            <MessageSquarePlus aria-hidden="true" data-icon="inline-start" />
            {t("playground.threads.new")}
          </Button>
        </div>

        {!agentReady ? (
          <Alert>
            <AlertTitle>{t("playground.noAgent")}</AlertTitle>
            <AlertDescription>
              <Link href={`/clients/${encodeURIComponent(refId)}/agent`} className="underline underline-offset-4">
                {t("playground.noAgent.cta")}
              </Link>
            </AlertDescription>
          </Alert>
        ) : null}

        {/* transcript */}
        {threads.length === 0 ? (
          <EmptyState
            icon={MessageSquarePlus}
            title={t("playground.threads.empty")}
            description={t("playground.threads.empty.body")}
            action={
              <Button onClick={() => void createThread()} disabled={busy}>
                {t("playground.threads.new")}
              </Button>
            }
          />
        ) : (
          <Card className="flex min-h-96 flex-col">
            <CardContent className="flex flex-1 flex-col gap-3 overflow-y-auto p-4" aria-label={t("playground.transcript.live")} aria-live="polite" aria-busy={running}>
              {!selected ? (
                <p className="m-auto text-sm text-muted-foreground">{t("playground.threads.select")}</p>
              ) : turns.length === 0 ? (
                <p className="m-auto max-w-prose text-center text-sm text-pretty text-muted-foreground">{t("playground.transcript.empty")}</p>
              ) : (
                <ol className="flex flex-col gap-3">
                  {turns.map((turn) => (
                    <li key={turn.runId} className="flex flex-col gap-2">
                      <div className="flex justify-end">
                        <div className="max-w-[80%] rounded-md bg-foreground px-3 py-2 text-sm whitespace-pre-wrap text-background">
                          <span className="sr-only">{t("playground.you")}: </span>
                          {turn.prompt}
                        </div>
                      </div>
                      <div className="flex justify-start">
                        <div className="max-w-[80%] rounded-md bg-muted px-3 py-2 text-sm whitespace-pre-wrap">
                          <span className="sr-only">{t("playground.agent")}: </span>
                          {turn.reply ||
                            (turn.status === "running" || turn.status === "pending" ? (
                              <span className="text-muted-foreground">{t("playground.thinking")}</span>
                            ) : turn.status === "cancelled" ? (
                              <span className="text-muted-foreground">{t("playground.run.cancelled")}</span>
                            ) : turn.status === "error" ? (
                              <span className="text-status-danger">{t("playground.run.error")}</span>
                            ) : null)}
                          {turn.reply && turn.status === "cancelled" ? <span className="block text-xs text-muted-foreground">{t("playground.run.cancelled")}</span> : null}
                          {turn.gap ? <span className="block text-xs text-status-warning">{t("playground.run.gap")}</span> : null}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              <div ref={bottomRef} />
            </CardContent>
            <div className="border-t border-border p-3">
              {exhausted ? (
                <p className="mb-2 text-sm text-status-danger" role="status">
                  {t("playground.composer.disabledCap")}
                </p>
              ) : null}
              {reconnecting ? (
                <p className="mb-2 text-xs text-muted-foreground" role="status">
                  {t("playground.run.reconnecting")}
                </p>
              ) : null}
              <div className="flex items-end gap-2">
                <Textarea
                  ref={composerRef}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={onKeyDown}
                  aria-label={t("playground.composer.label")}
                  placeholder={t("playground.composer.placeholder")}
                  disabled={!selectedId || exhausted || !agentReady}
                  maxLength={MAX_PROMPT + 1}
                  aria-invalid={text.length > MAX_PROMPT || undefined}
                  rows={2}
                  className="min-h-16 flex-1 resize-y"
                />
                {running ? (
                  <Button variant="outline" onClick={() => void stop()} aria-label={t("playground.composer.stop")}>
                    <Square aria-hidden="true" data-icon="inline-start" />
                    {t("playground.composer.stop")}
                  </Button>
                ) : (
                  <Button onClick={() => void send()} disabled={!canSend || !text.trim() || text.length > MAX_PROMPT} aria-label={t("playground.composer.send")}>
                    <Send aria-hidden="true" data-icon="inline-start" />
                    {t("playground.composer.send")}
                  </Button>
                )}
              </div>
              {text.length > MAX_PROMPT ? (
                <p className="mt-1 text-xs text-status-danger" role="alert">
                  {t("playground.composer.tooLong")}
                </p>
              ) : null}
            </div>
          </Card>
        )}
      </section>

      <aside className="flex min-w-0 flex-col gap-4" aria-label={t("playground.inspector")}>
        <Card>
          <CardContent className="pt-4">
            <BudgetBar budget={budget} error={budgetError} onRetry={() => void refreshBudget()} />
            <p className="mt-2 text-xs text-pretty text-muted-foreground">{t("playground.budget.hint")}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("playground.inspector")}</CardTitle>
            {selected?.last_run_at ? <p className="text-xs text-muted-foreground">{formatRelative(selected.last_run_at, locale)}</p> : null}
          </CardHeader>
          <CardContent>
            <TurnInspector turn={lastTurn} />
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
