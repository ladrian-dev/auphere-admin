"use client";

import { Info } from "lucide-react";
import * as React from "react";

import { Button, EmptyState, ErrorState, Skeleton } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { ConfirmCard } from "./confirm-card";
import { IntakeCard } from "./intake-card";
import { PlanCard } from "./plan-card";
import { type CompanionState, thinkingToolCount } from "./state";
import { Thinking } from "./thinking";
import { ToolCard } from "./tool-card";
import type { Decision, IntakeSlot } from "./types";
import { VerifyTable } from "./verify-table";

/**
 * The timeline (§14). `role="log"` with `aria-live="polite"` so a screen
 * reader follows the conversation without being interrupted mid-sentence.
 *
 * **`aria-live="assertive"` is used exactly once, for `hitl.requested`**,
 * and it lives in its own node rather than on the log. Assertive interrupts
 * whatever the user is hearing; that is justified for "I need your
 * confirmation and the graph is frozen until you answer", and for nothing
 * else. Putting it on the log itself would make every token of streamed
 * text interrupt, which is how a live region becomes something people turn
 * off.
 *
 * The five Hurff states all live here, because they are states of this
 * region, not of the drawer: loading (skeleton bubbles, never a spinner),
 * empty (three suggestions derived from the real page context), error
 * (reason + retry), partial (a run already under way after reconnecting,
 * with what is already done visible), ideal.
 */
type Props = {
  state: CompanionState;
  status: "loading" | "error" | "ready";
  errorDetail: string | null;
  partial: boolean;
  currentUserId: string | null;
  deciding: boolean;
  decisionFailure: { status: number; code: string | null } | null;
  suggestions: string[];
  onRetry: () => void;
  onSuggestion: (text: string) => void;
  onAnswerSlot: (slot: IntakeSlot) => void;
  onDecide: (actionId: string, decision: Decision, note?: string) => void;
};

export function Timeline({
  state,
  status,
  errorDetail,
  partial,
  currentUserId,
  deciding,
  decisionFailure,
  suggestions,
  onRetry,
  onSuggestion,
  onAnswerSlot,
  onDecide,
}: Props) {
  const t = useT();
  const bottomRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    // Optional call: jsdom does not implement `scrollIntoView`, and
    // autoscrolling is a convenience — never a reason for the log to throw.
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [state.items.length]);

  // The one assertive announcement of the whole drawer.
  const awaiting = React.useMemo(
    () => state.items.find((i) => i.kind === "action" && i.state === "pending"),
    [state.items],
  );

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {/* No `role` on purpose: `role="status"` carries an implicit polite
          politeness that would contradict the explicit assertive, and
          `role="alert"` would collide with the ErrorState below. A bare
          live region is unambiguous. */}
      <div aria-live="assertive" aria-atomic="true" className="sr-only">
        {awaiting && awaiting.kind === "action"
          ? t("companion.confirm.live", { title: awaiting.title })
          : ""}
      </div>

      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-label={t("companion.title")}
        aria-busy={status === "loading"}
        className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-3"
      >
        {status === "loading" ? <LoadingBubbles /> : null}

        {status === "error" ? (
          <ErrorState
            title={t("companion.error.title")}
            description={errorDetail === "network" ? t("companion.error.network") : errorDetail}
            onRetry={onRetry}
            retryLabel={t("common.retry")}
          />
        ) : null}

        {status === "ready" && state.items.length === 0 ? (
          <EmptyState
            title={t("companion.empty.title")}
            description={t("companion.empty.body")}
            action={
              <div className="flex min-w-0 flex-col gap-2">
                <p className="text-xs text-muted-foreground">{t("companion.empty.suggestions")}</p>
                {suggestions.map((s) => (
                  <Button key={s} variant="outline" size="sm" className="h-auto min-h-8 py-2 text-left" onClick={() => onSuggestion(s)}>
                    <span className="text-pretty">{s}</span>
                  </Button>
                ))}
              </div>
            }
          />
        ) : null}

        {status === "ready" && partial && state.items.length > 0 ? (
          <div className="mb-3 min-w-0 rounded-sm border border-border bg-muted px-3 py-2">
            <p className="flex min-w-0 items-start gap-2 text-xs text-muted-foreground">
              <Info aria-hidden="true" className="mt-px size-3 shrink-0" />
              <span className="min-w-0 text-pretty">
                <span className="font-medium text-foreground">{t("companion.partial.title")}</span>{" "}
                {t("companion.partial.body")}
              </span>
            </p>
          </div>
        ) : null}

        <ol className="min-w-0 space-y-3">
          {state.items.map((item) => (
            <li key={item.id} className="min-w-0">
              {item.kind === "user" ? (
                <div className="flex min-w-0 justify-end">
                  <p className="min-w-0 max-w-[85%] rounded-md bg-primary px-3 py-2 text-sm text-pretty break-words text-primary-foreground">
                    {item.text}
                  </p>
                </div>
              ) : null}

              {item.kind === "assistant" ? (
                <p className="min-w-0 text-sm whitespace-pre-wrap text-pretty break-words text-foreground">{item.text}</p>
              ) : null}

              {item.kind === "thinking" ? (
                <Thinking
                  text={item.text}
                  live={item.endedAt === null}
                  seconds={item.endedAt === null ? null : Math.max(1, Math.round((item.endedAt - item.startedAt) / 1000))}
                  toolCount={thinkingToolCount(state, item.id)}
                />
              ) : null}

              {item.kind === "tool" ? (
                <ToolCard item={item} citation={item.citationId ? (state.citations[item.citationId] ?? null) : null} />
              ) : null}

              {item.kind === "plan" ? (
                <PlanCard
                  steps={item.steps}
                  risk={item.risk}
                  reversible={item.reversible}
                  estimatedTokens={item.estimatedTokens}
                />
              ) : null}

              {item.kind === "intake" ? <IntakeCard slots={item.slots} onAnswer={onAnswerSlot} /> : null}

              {item.kind === "action" ? (
                <ConfirmCard
                  item={item}
                  currentUserId={currentUserId}
                  busy={deciding}
                  failure={item.state === "pending" ? decisionFailure : null}
                  onDecide={(decision, note) => onDecide(item.id, decision, note)}
                />
              ) : null}

              {item.kind === "verify" ? <VerifyTable checks={item.checks} ok={item.ok} /> : null}

              {item.kind === "notice" ? (
                <p
                  className={`min-w-0 rounded-sm border border-border px-3 py-2 text-xs text-pretty ${
                    item.code === "error" ? "text-status-danger" : "text-muted-foreground"
                  }`}
                >
                  {t(`companion.notice.${item.code}` as const)}
                  {item.detail && item.code === "error" ? <span className="mt-1 block font-mono">{item.detail}</span> : null}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

/**
 * Skeleton bubbles sized like real ones — §14 says a skeleton, not a
 * spinner: it tells you what is coming and it does not spin forever.
 */
function LoadingBubbles() {
  const t = useT();
  return (
    <div role="status" className="min-w-0 space-y-3" aria-label={t("companion.loading")}>
      <div className="flex justify-end">
        <Skeleton className="h-8 w-40 rounded-md" />
      </div>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-16 w-full rounded-sm" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}
