"use client";

import { ChevronRight } from "lucide-react";
import * as React from "react";

import { useT } from "@/i18n/client";

/**
 * Collapsible reasoning (§8.2 of the research).
 *
 * Collapsed by default with a summary line, expandable in one click. Both
 * halves of that are deliberate: expanded always, a 480 px drawer becomes
 * unreadable; hidden entirely, the user cannot audit why the agent did
 * what it did — and auditing is exactly what builds trust.
 *
 * The reasoning is never persisted beyond the session (it is expensive to
 * store and its digressions later read as commitments), so after a reload
 * the REST history carries no `reasoning.delta` and this block simply does
 * not appear. It never renders a fake "Thought for 0 s".
 */
export function Thinking({
  text,
  seconds,
  toolCount,
  live,
}: {
  text: string;
  seconds: number | null;
  toolCount: number;
  live: boolean;
}) {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const id = React.useId();

  const summary = live
    ? t("companion.thinking.live")
    : toolCount === 0
      ? t("companion.thinking.summary", { seconds: seconds ?? 0 })
      : toolCount === 1
        ? t("companion.thinking.summaryOneTool", { seconds: seconds ?? 0 })
        : t("companion.thinking.summaryWithTools", { seconds: seconds ?? 0, n: toolCount });

  return (
    <div className="min-w-0">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-6 w-full min-w-0 items-center gap-1 rounded-sm text-left text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <ChevronRight
          aria-hidden="true"
          className={`size-3 shrink-0 transition-transform motion-reduce:transition-none ${open ? "rotate-90" : ""}`}
        />
        <span className="min-w-0 truncate">{summary}</span>
        <span className="sr-only">{t("companion.thinking.expand")}</span>
      </button>
      {open ? (
        <div id={id} className="mt-1 min-w-0 border-l border-border pl-3">
          <p className="min-w-0 text-xs whitespace-pre-wrap text-pretty break-words text-muted-foreground">{text}</p>
          <p className="mt-1 text-xs text-muted-foreground/70">{t("companion.thinking.note")}</p>
        </div>
      ) : null}
    </div>
  );
}
