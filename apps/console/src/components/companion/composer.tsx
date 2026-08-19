"use client";

import { PauseCircle, Send, Square } from "lucide-react";
import * as React from "react";

import { Button, Textarea, formatDate, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

import type { BudgetPause } from "./types";

export const MAX_PROMPT = 8000;

/**
 * The composer: text, the two modes, and Send / Stop.
 *
 * **Stop calls `DELETE …/runs/{id}` and nothing else.** Aborting the
 * stream's `fetch` only tears down this view — the run carries on
 * server-side. That is a property of resumable streams, not a bug to work
 * around, and an explicit cancellation endpoint is the documented answer.
 *
 * Consult vs Build is an act of the USER, never of the model (§4.2).
 * Consult is the default because it is safe by omission: read-only tools.
 *
 * **The cap is a pause, not an error** (§6 of CONTRACT-V2). When it is
 * reached, only this box goes quiet: the thread stays, the history stays,
 * and a pending confirmation stays answerable, because answering one does
 * not start new work. The explanation says what unblocks it — raising the
 * cap — because a disabled control with no way out is a wall. And none of
 * it is red: red for something that is fixed by raising a number teaches
 * people to fear the tool.
 */
type Props = {
  value: string;
  mode: "consult" | "build";
  busy: boolean;
  blocked: boolean;
  /** The budget snapshot of §6.4, when we have it (the `budget.paused`
   *  event, or the body of the 409). Carries the numbers. */
  paused: BudgetPause | null;
  /** The degenerate case: `budget.updated.exhausted` told us the cap was
   *  reached but we have no snapshot. Same state, fewer specifics. */
  exhausted: boolean;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  onMode: (mode: "consult" | "build") => void;
};

export const Composer = React.forwardRef<HTMLTextAreaElement, Props>(function Composer(
  { value, mode, busy, blocked, paused, exhausted, onChange, onSend, onStop, onMode },
  ref,
) {
  const t = useT();
  const locale = useLocale();
  const tooLong = value.length > MAX_PROMPT;
  const halted = paused !== null || exhausted;
  const canSend = value.trim().length > 0 && !tooLong && !busy && !blocked && !halted;
  const hintId = React.useId();

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (canSend) onSend();
    }
  }

  return (
    <div className="min-w-0 border-t border-border px-4 py-3">
      <div className="flex min-w-0 items-center gap-2 pb-2">
        <span id={hintId} className="sr-only">
          {mode === "consult" ? t("companion.mode.consult.hint") : t("companion.mode.build.hint")}
        </span>
        {/* `aria-pressed` toggles rather than `role="radio"`: the ARIA radio
            pattern owes a roving tabindex and arrow-key navigation, and
            claiming the role without implementing it is worse than not
            claiming it. Both buttons are reachable by Tab, which is the
            same affordance the console's thread chips already use. */}
        <div
          role="group"
          aria-label={t("companion.mode")}
          className="flex min-w-0 items-center gap-1 rounded-full border border-border p-1"
        >
          {(["consult", "build"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              aria-describedby={hintId}
              onClick={() => onMode(m)}
              className={`min-h-6 rounded-full px-3 text-xs transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none ${
                mode === m ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t(`companion.mode.${m}` as const)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-w-0 items-end gap-2">
        <Textarea
          ref={ref}
          rows={2}
          value={value}
          maxLength={MAX_PROMPT + 1}
          disabled={halted}
          aria-label={t("companion.composer.label")}
          aria-invalid={tooLong || undefined}
          placeholder={t("companion.composer.placeholder")}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          className="min-h-16 flex-1 text-sm"
        />
        {busy ? (
          <Button variant="outline" size="icon" aria-label={t("companion.composer.stop")} onClick={onStop}>
            <Square aria-hidden="true" />
          </Button>
        ) : (
          <Button size="icon" aria-label={t("companion.composer.send")} disabled={!canSend} onClick={onSend}>
            <Send aria-hidden="true" />
          </Button>
        )}
      </div>

      {tooLong ? (
        <p role="alert" className="mt-1 text-xs text-status-danger">
          {t("companion.composer.tooLong")}
        </p>
      ) : null}
      {blocked ? <p className="mt-1 text-xs text-pretty text-muted-foreground">{t("companion.composer.blocked")}</p> : null}

      {/* A change in what you CAN DO, not only in what you see, so it is
          announced. Polite: `assertive` belongs to `hitl.requested` alone
          (§14), and this can wait for a gap in the speech. */}
      {halted ? (
        <div role="status" aria-live="polite" className="mt-2 min-w-0 rounded-sm border border-border bg-muted px-3 py-2">
          <p className="flex min-w-0 items-start gap-2 text-xs text-muted-foreground">
            <PauseCircle aria-hidden="true" className="mt-px size-4 shrink-0" />
            <span className="min-w-0 text-pretty">
              <span className="font-medium text-foreground">{t("companion.paused.title")}</span>{" "}
              {paused
                ? t("companion.paused.body", {
                    used: formatNumber(paused.used, locale),
                    cap: formatNumber(paused.cap, locale),
                  })
                : t("companion.meter.exhausted.body")}
            </span>
          </p>
          {/* Without the way out, a disabled box is just a wall. */}
          <p className="mt-1 pl-5 text-xs text-pretty text-muted-foreground">{t("companion.paused.unblock")}</p>
          {paused?.resetsAt ? (
            <p className="mt-px pl-5 text-xs text-muted-foreground">
              {t("companion.meter.month.resets", { date: formatDate(paused.resetsAt, locale) })}
            </p>
          ) : null}
          {/* The thread is not gone and neither is anything owed. */}
          <p className="mt-1 pl-5 text-xs text-pretty text-muted-foreground">{t("companion.paused.kept")}</p>
        </div>
      ) : null}
    </div>
  );
});
