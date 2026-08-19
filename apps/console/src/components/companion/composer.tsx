"use client";

import { Send, Square } from "lucide-react";
import * as React from "react";

import { Button, Textarea } from "@nexus/ui";

import { useT } from "@/i18n/client";

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
 */
type Props = {
  value: string;
  mode: "consult" | "build";
  busy: boolean;
  blocked: boolean;
  exhausted: boolean;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  onMode: (mode: "consult" | "build") => void;
};

export const Composer = React.forwardRef<HTMLTextAreaElement, Props>(function Composer(
  { value, mode, busy, blocked, exhausted, onChange, onSend, onStop, onMode },
  ref,
) {
  const t = useT();
  const tooLong = value.length > MAX_PROMPT;
  const canSend = value.trim().length > 0 && !tooLong && !busy && !blocked && !exhausted;
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
          disabled={exhausted}
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
      {exhausted ? (
        <p className="mt-1 text-xs text-pretty text-status-danger">{t("companion.meter.exhausted.body")}</p>
      ) : null}
    </div>
  );
});
