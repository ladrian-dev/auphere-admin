"use client";

import { HelpCircle } from "lucide-react";

import { Badge } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { optionalKey } from "./i18n";
import type { IntakeSlot } from "./types";

/**
 * The intake card (§2.2 of the contract).
 *
 * **Chips you can answer, not a form.** The distinction is the whole
 * point: a form implies a fixed order, mandatory fields and a Submit
 * button, and it turns a conversation into paperwork. Here each missing
 * piece is a chip that drops its label into the composer, and the user
 * answers in their own words, in any order, or ignores it and says
 * something else entirely.
 *
 * Answering is NOT a new endpoint either — it is an ordinary `POST …/runs`
 * in the same thread. The intake is context of the conversation, not
 * server-side state. (CO-06 turns it into a state machine; not here.)
 *
 * `key` is stable, so we can carry our own copy for the ones we know;
 * anything else falls back to the backend's `label` and `why`.
 */
export function IntakeCard({ slots, onAnswer }: { slots: IntakeSlot[]; onAnswer: (slot: IntakeSlot) => void }) {
  const t = useT();

  return (
    <section aria-label={t("companion.intake.title")} className="min-w-0 rounded-sm border border-border bg-card p-3">
      <div className="flex min-w-0 items-center gap-2">
        <HelpCircle aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h3 className="min-w-0 flex-1 truncate text-sm font-medium">{t("companion.intake.title")}</h3>
      </div>
      <p className="mt-1 text-xs text-pretty text-muted-foreground">{t("companion.intake.body")}</p>

      <ul className="mt-3 min-w-0 space-y-2">
        {slots.map((slot) => {
          const localKey = optionalKey(`companion.intake.slot.${slot.key}`);
          const label = localKey ? t(localKey) : slot.label || slot.key;
          return (
            <li key={slot.key} className="min-w-0">
              <button
                type="button"
                onClick={() => onAnswer({ ...slot, label })}
                aria-label={t("companion.intake.answer", { label })}
                className="flex min-h-8 w-full min-w-0 items-center gap-2 rounded-sm border border-border px-2 py-1 text-left transition-colors hover:border-primary hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">{label}</span>
                <Badge variant="outline" className="shrink-0">
                  {slot.required ? t("companion.intake.required") : t("companion.intake.optional")}
                </Badge>
              </button>
              {slot.why ? <p className="mt-1 pl-2 text-xs text-pretty text-muted-foreground">{slot.why}</p> : null}
              {slot.examples.length > 0 ? (
                <p className="mt-1 pl-2 text-xs text-pretty text-muted-foreground/80">
                  {t("companion.intake.examples")}: {slot.examples.join(" · ")}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
