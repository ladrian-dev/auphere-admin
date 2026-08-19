"use client";

import { HelpCircle, ShieldAlert } from "lucide-react";

import { Badge } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { optionalKey } from "./i18n";
import type { IntakeSlot, WorkKind } from "./types";

/**
 * The intake card (§2.2 of CONTRACT-V1, extended by §3 of CONTRACT-V2).
 *
 * **Chips you can answer, not a form.** The distinction is the whole
 * point: a form implies a fixed order, mandatory fields and a Submit
 * button, and it turns a conversation into paperwork. Here each missing
 * piece is a chip that drops its label into the composer, and the user
 * answers in their own words, in any order, or ignores it and says
 * something else entirely.
 *
 * Answering is NOT a new endpoint either — it is an ordinary `POST …/runs`
 * in the same thread. (CO-06 persists the intake so it survives a reload;
 * that is state on the server, not a second way in from here.)
 *
 * `work_kind` (v2 §3.1) titles the group: *"To create the client I still
 * need…"* rather than a generic heading. A value outside the closed enum
 * of §3.2 falls back to the generic title, never to the identifier.
 *
 * `key` is stable and closed per work kind (§3.3), so we carry our own
 * copy for all twelve; anything else falls back to the backend's `label`
 * and `why`.
 */

/**
 * The field nobody writes and the one that causes the incidents (§7.1).
 * It is mandatory on purpose and it is painted differently on purpose —
 * see `SlotChip` for the three differences and why each one is earned.
 */
const HIGHLIGHT = "forbidden_behaviour";

export function IntakeCard({
  slots,
  workKind,
  onAnswer,
}: {
  slots: IntakeSlot[];
  workKind: WorkKind | null;
  onAnswer: (slot: IntakeSlot) => void;
}) {
  const t = useT();

  const titleKey = workKind ? optionalKey(`companion.intake.title.${workKind}`) : null;
  const title = titleKey ? t(titleKey) : t("companion.intake.title");

  // The order of a list is an argument. Burying "what the agent must NOT
  // do" behind "time zone" turns the one field that prevents incidents
  // into paperwork, so it leads regardless of what the backend sent.
  const ordered = [...slots].sort((a, b) => Number(b.key === HIGHLIGHT) - Number(a.key === HIGHLIGHT));

  return (
    <section aria-label={title} className="min-w-0 rounded-sm border border-border bg-card p-3">
      <div className="flex min-w-0 items-center gap-2">
        <HelpCircle aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h3 className="min-w-0 flex-1 text-sm font-medium text-pretty">{title}</h3>
      </div>
      <p className="mt-1 text-xs text-pretty text-muted-foreground">{t("companion.intake.body")}</p>

      <ul className="mt-3 min-w-0 space-y-2">
        {ordered.map((slot) => (
          <SlotChip key={slot.key} slot={slot} onAnswer={onAnswer} />
        ))}
      </ul>
    </section>
  );
}

function SlotChip({ slot, onAnswer }: { slot: IntakeSlot; onAnswer: (slot: IntakeSlot) => void }) {
  const t = useT();
  const highlighted = slot.key === HIGHLIGHT;

  const localKey = optionalKey(`companion.intake.slot.${slot.key}`);
  const label = localKey ? t(localKey) : slot.label || slot.key;
  const whyKey = optionalKey(`companion.intake.why.${slot.key}`);
  const why = whyKey ? t(whyKey) : slot.why;

  return (
    <li className="min-w-0">
      <button
        type="button"
        onClick={() => onAnswer({ ...slot, label })}
        aria-label={t("companion.intake.answer", { label })}
        className={[
          "flex min-h-8 w-full min-w-0 items-center gap-2 rounded-sm border px-2 py-1 text-left transition-colors",
          "focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
          highlighted
            ? "border-status-warning/60 bg-status-warning/5 hover:border-status-warning hover:bg-status-warning/10"
            : "border-border hover:border-primary hover:bg-muted",
        ].join(" ")}
      >
        {/* The tone is never the only carrier of the message (WCAG 1.4.1):
            the icon and the badge below say the same thing in words. */}
        {highlighted ? (
          <ShieldAlert aria-hidden="true" className="size-4 shrink-0 text-status-warning" />
        ) : null}
        {/* Wraps, never truncates. The label IS the question being asked,
            so cutting it off loses the thing the chip exists to say — and
            a German or Spanish label runs ~30 % longer than the English
            one this was sized against. `min-w-0` keeps the flex child from
            forcing the row wider than the drawer at 360 px. */}
        <span className="min-w-0 flex-1 text-xs font-medium text-pretty text-foreground">{label}</span>
        <Badge variant="outline" className="shrink-0">
          {highlighted
            ? t("companion.intake.keyField")
            : slot.required
              ? t("companion.intake.required")
              : t("companion.intake.optional")}
        </Badge>
      </button>

      {/* On the highlighted row the "why" IS the argument, not a footnote,
          so it stays at full contrast and never gets truncated. */}
      {why ? (
        <p className={`mt-1 pl-2 text-xs text-pretty ${highlighted ? "text-foreground" : "text-muted-foreground"}`}>
          {why}
        </p>
      ) : null}

      {slot.examples.length > 0 ? (
        <p className={`mt-1 pl-2 text-xs text-pretty ${highlighted ? "text-muted-foreground" : "text-muted-foreground/80"}`}>
          {t("companion.intake.examples")}: {slot.examples.join(" · ")}
        </p>
      ) : null}
    </li>
  );
}
