"use client";

import { AlertTriangle } from "lucide-react";
import * as React from "react";

import { Button, formatDateTime } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { AgentDraft, DraftChange } from "@/lib/backend/agent-draft-types";

import { conflictTitle, fieldLabels, joinList, overlap, theirFields } from "./fields";

type Props = {
  /** The draft as it is now (the 412's `current`). */
  current: AgentDraft;
  /** What changed after the revision this screen read. */
  changes: readonly DraftChange[];
  /** The fields this person was about to save. */
  mine: readonly string[];
  /** Their pending instructions, to compare when both changed them. */
  myPrompt?: string;
  busy: boolean;
  onKeepMine: () => void;
  onKeepTheirs: () => void;
};

/**
 * «Hay cambios más nuevos de Luis» (spec 047, historia 2, escenario 2).
 *
 * The second save was refused before anything landed, so this says the two
 * things a person needs to decide: what the other one changed and what they
 * were about to save — and, where both touched the same field, that saving
 * theirs on top replaces the other's there. Nothing is decided for them:
 * «Guardar los míos encima» retries with the new revision, «Quedarme con los
 * suyos» drops what they had typed. Focus moves here when it appears.
 */
export function DraftConflictNotice({ current, changes, mine, myPrompt, busy, onKeepMine, onKeepTheirs }: Props) {
  const t = useT();
  const locale = useLocale();
  const headingId = React.useId();
  const heading = React.useRef<HTMLHeadingElement>(null);
  React.useEffect(() => {
    heading.current?.focus();
  }, []);

  const and = t("agents.draft.bar.and");
  const title = conflictTitle(changes);
  const theirs = theirFields(changes);
  const both = overlap(theirs, mine);
  const last = changes[changes.length - 1];
  const theirLabels = fieldLabels(theirs, t);
  const myLabels = fieldLabels(mine, t);
  const comparePrompt = myPrompt !== undefined && both.includes("system_prompt");

  return (
    <section
      aria-labelledby={headingId}
      data-slot="draft-conflict"
      className="flex min-w-0 flex-col gap-3 rounded-md border border-status-warning-border bg-status-warning-bg p-3 text-sm text-foreground"
    >
      <div className="flex min-w-0 items-start gap-2">
        <AlertTriangle aria-hidden="true" className="mt-1 size-4 shrink-0 text-warning" />
        <div className="flex min-w-0 flex-col gap-1">
          <h2 id={headingId} ref={heading} tabIndex={-1} className="font-medium text-balance outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {t(title.key, { who: joinList(title.who, and) })}
          </h2>
          <p className="max-w-prose text-pretty text-muted-foreground">{t("agents.draft.conflict.body")}</p>
        </div>
      </div>

      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
        <div className="min-w-0">
          <h3 className="text-xs font-medium text-muted-foreground">
            {t("agents.draft.conflict.theirs")}
            {last ? <span className="font-normal tabular-nums"> · {formatDateTime(last.at, locale)}</span> : null}
          </h3>
          <FieldList labels={theirLabels} empty={t("agents.draft.conflict.nothing")} />
        </div>
        <div className="min-w-0">
          <h3 className="text-xs font-medium text-muted-foreground">{t("agents.draft.conflict.mine")}</h3>
          <FieldList labels={myLabels} empty={t("agents.draft.conflict.nothing")} />
        </div>
      </div>

      {both.length ? (
        <p className="max-w-prose text-pretty" data-slot="draft-conflict-both">
          {t("agents.draft.conflict.both", { fields: joinList(fieldLabels(both, t), and) })}
        </p>
      ) : null}

      {comparePrompt ? (
        <details className="min-w-0">
          <summary className="cursor-pointer text-muted-foreground">{t("agents.draft.conflict.comparePrompt")}</summary>
          <div className="mt-2 grid min-w-0 gap-2 md:grid-cols-2">
            <figure className="min-w-0">
              <figcaption className="text-xs text-muted-foreground">{t("agents.draft.conflict.theirPrompt")}</figcaption>
              <pre className="max-h-64 overflow-auto rounded-md bg-card p-2 font-mono text-xs whitespace-pre-wrap">{current.system_prompt}</pre>
            </figure>
            <figure className="min-w-0">
              <figcaption className="text-xs text-muted-foreground">{t("agents.draft.conflict.myPrompt")}</figcaption>
              <pre className="max-h-64 overflow-auto rounded-md bg-card p-2 font-mono text-xs whitespace-pre-wrap">{myPrompt}</pre>
            </figure>
          </div>
        </details>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button onClick={onKeepMine} loading={busy}>
          {t("agents.draft.conflict.keepMine")}
        </Button>
        <Button variant="outline" onClick={onKeepTheirs} disabled={busy}>
          {t("agents.draft.conflict.keepTheirs")}
        </Button>
      </div>
    </section>
  );
}

function FieldList({ labels, empty }: { labels: string[]; empty: string }) {
  if (!labels.length) return <p className="text-muted-foreground">{empty}</p>;
  return (
    <ul className="mt-1 flex min-w-0 flex-wrap gap-1">
      {labels.map((label) => (
        <li key={label} className="rounded-sm bg-card px-2 py-1 text-xs ring-1 ring-foreground/10">
          {label}
        </li>
      ))}
    </ul>
  );
}
