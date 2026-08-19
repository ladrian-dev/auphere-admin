"use client";

import { Check, ExternalLink, FlaskConical, Info, X } from "lucide-react";
import Link from "next/link";

import { formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

import { optionalKey } from "./i18n";
import type { Trial } from "./types";

/**
 * The playground trial panel — `verify.result.trial` (§7 of CONTRACT-V2).
 *
 * Three rules from the contract, and each one is the kind that gets lost
 * in a refactor unless it is written down next to the code:
 *
 * 1. **`null` and `{ran: false}` are not the same thing.** `null` means
 *    the action admits no trial at all (an `invite`, a `usage_alerts`) and
 *    paints NOTHING. `{ran: false}` means it does admit one and none was
 *    run — and that is the notice publishing warns about. The caller
 *    passes `null` for the first case; this component never renders for
 *    it. Collapsing the two would silently delete the warning.
 *
 * 2. **`trial` never carries the draft agent's reply.** Not whole, not
 *    trimmed, not summarised. It carries `probe` (written by the
 *    Companion, like `citation.claim`, so safe to paint), named assertions
 *    and metadata. This panel must not pretend otherwise: it says out loud
 *    that the conversation lives in the playground thread, and links there.
 *
 * 3. `checks[].name` is a stable English identifier we translate;
 *    `expected` and `actual` are always strings.
 *
 * Produced by deterministic code — a turn is sent and assertions are
 * compared. No subagent, no "check your work" instruction (C5).
 */
export function TrialPanel({
  trial,
  clientRef,
}: {
  trial: Trial;
  /**
   * Needed to build the playground URL, and NOT part of `verify.result`.
   * The caller correlates it back through `action_id`; when it cannot,
   * this is `null` and the thread id is shown copyable instead of behind
   * a link that goes nowhere.
   */
  clientRef: string | null;
}) {
  const t = useT();
  const locale = useLocale();

  // §7: "it admits a trial and it was not done" — an advisory, not a
  // failure. Neutral tone: nothing went wrong, something was skipped.
  if (!trial.ran) {
    return (
      <div className="mt-3 min-w-0 rounded-sm border border-border bg-muted px-3 py-2">
        <p className="flex min-w-0 items-start gap-2 text-xs text-muted-foreground">
          <Info aria-hidden="true" className="mt-px size-3 shrink-0" />
          <span className="min-w-0 text-pretty">
            <span className="font-medium text-foreground">{t("companion.trial.notRun.title")}</span>{" "}
            {t("companion.trial.notRun.body")}
          </span>
        </p>
      </div>
    );
  }

  const ok = trial.ok !== false;

  return (
    <section
      aria-label={t("companion.trial.title")}
      className={`mt-3 min-w-0 rounded-sm border bg-card p-3 ${ok ? "border-border" : "border-status-danger/40"}`}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <FlaskConical aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h4 className="min-w-0 flex-1 text-sm font-medium text-pretty">{t("companion.trial.title")}</h4>
        <span className={`shrink-0 text-xs font-medium ${ok ? "text-status-positive" : "text-status-danger"}`}>
          {ok ? t("companion.trial.ok") : t("companion.trial.failed")}
        </span>
      </div>

      <p className="mt-1 text-xs text-muted-foreground">
        {t("companion.trial.summary", {
          turns: trial.turns.length,
          tokens: trial.tokens === null ? "—" : formatNumber(trial.tokens, locale),
        })}
      </p>

      {trial.turns.length > 0 ? (
        <ol className="mt-2 min-w-0 space-y-2">
          {trial.turns.map((turn) => (
            <li key={turn.index} className="min-w-0 rounded-sm border border-border p-2">
              <div className="flex min-w-0 items-start gap-2">
                {turn.ok ? (
                  <Check aria-hidden="true" className="mt-px size-4 shrink-0 text-status-positive" />
                ) : (
                  <X aria-hidden="true" className="mt-px size-4 shrink-0 text-status-danger" />
                )}
                <p className="min-w-0 flex-1 text-xs text-pretty break-words text-foreground">
                  {/* `probe` is written by the Companion — safe to paint. */}
                  {turn.probe}
                  <span className="sr-only">
                    {" "}
                    — {turn.ok ? t("companion.trial.turn.ok") : t("companion.trial.turn.failed")}
                  </span>
                </p>
                {turn.latencyMs !== null ? (
                  <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
                    {t("companion.trial.latency", { ms: formatNumber(turn.latencyMs, locale) })}
                  </span>
                ) : null}
              </div>

              {turn.checks.length > 0 ? (
                <div className="mt-1 min-w-0 overflow-x-auto">
                  <table className="w-full min-w-0 text-xs">
                    <caption className="sr-only">
                      {t("companion.trial.checks.caption", { index: turn.index })}
                    </caption>
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th scope="col" className="py-1 pr-3 font-medium">
                          {t("companion.trial.check")}
                        </th>
                        <th scope="col" className="py-1 pr-3 font-medium">
                          {t("companion.verify.expected")}
                        </th>
                        <th scope="col" className="py-1 font-medium">
                          {t("companion.verify.actual")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {turn.checks.map((c) => {
                        const labelKey = optionalKey(`companion.trial.check.${c.name}`);
                        return (
                          <tr key={c.name} className="border-t border-border">
                            <th scope="row" className="py-1 pr-3 text-left font-normal text-foreground">
                              {labelKey ? t(labelKey) : c.name}
                            </th>
                            <td className="py-1 pr-3 font-mono tabular-nums text-muted-foreground">{c.expected}</td>
                            <td
                              className={`py-1 font-mono tabular-nums ${c.ok ? "text-status-positive" : "text-status-danger"}`}
                            >
                              {c.actual}
                              <span className="sr-only">
                                {" "}
                                — {c.ok ? t("companion.verify.ok") : t("companion.verify.failed")}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      {/* Rule 2, said out loud. The panel does not hold the conversation
          and must not look as if it did. */}
      <p className="mt-2 text-xs text-pretty text-muted-foreground">{t("companion.trial.noTranscript")}</p>
      <TrialThreadLink threadId={trial.threadId} clientRef={clientRef} />
    </section>
  );
}

/**
 * The way into the playground thread.
 *
 * With a `client_ref` we can build the route; without one we cannot, so
 * the thread id is shown selectable instead. **A dead link is worse than
 * no link** — it looks like a way out and is not.
 *
 * Note for Phase 2: the playground page does not read a thread parameter
 * from the URL today (`components/playground/playground.tsx` keeps the
 * selected thread in local state), so `?thread=` is inert until that page
 * honours it. That file is outside this agent's zone.
 */
function TrialThreadLink({ threadId, clientRef }: { threadId: string | null; clientRef: string | null }) {
  const t = useT();
  if (!threadId) return null;

  if (!clientRef) {
    return (
      <p className="mt-1 min-w-0 text-xs text-pretty text-muted-foreground">
        {t("companion.trial.threadId")} <span className="font-mono break-all select-all">{threadId}</span>
      </p>
    );
  }

  const href = `/clients/${encodeURIComponent(clientRef)}/playground?thread=${encodeURIComponent(threadId)}`;
  return (
    // `next/link`, not a bare anchor: the drawer is mounted in the console
    // layout, so a client navigation keeps it open — you can read the
    // trial and go look at the thread without losing the conversation. A
    // full page load would tear the drawer down and drop the run you were
    // following.
    <Link
      href={href}
      className="mt-1 inline-flex min-h-6 items-center gap-1 text-xs text-primary underline underline-offset-2 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {t("companion.trial.openThread")}
      <ExternalLink aria-hidden="true" className="size-3 shrink-0" />
    </Link>
  );
}
