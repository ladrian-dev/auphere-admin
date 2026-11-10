"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Input, Label, StatusDot } from "@nexus/ui";

import { saveDraftAction } from "@/app/(console)/clients/[ref]/agent/actions";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { AgentDraft, DraftChange, DraftPatch } from "@/lib/backend/agent-draft-types";

import { DraftConflictNotice } from "./conflict-notice";
import { SECTION_ORDER, usePendingFields, useRequiredDraftEdits } from "./draft-edits";
import { joinList } from "./fields";

type Conflict = { current: AgentDraft; changes: DraftChange[]; patch: DraftPatch; mine: string[] };

/**
 * The one save bar of the agent page (spec 047, historia 2).
 *
 * The instructions and the settings used to have a button each, and saving
 * one after the other left the first change in a version nobody would
 * publish. Now each editor only says what is pending; this bar collects it,
 * sends ONE write into the agent's draft with the revision the page read, and
 * on a 412 shows what the other person changed next to what this one was
 * about to save (`DraftConflictNotice`). Nothing is lost on either side:
 * the refused write did not land, and the screen keeps what was typed.
 *
 * It stays at the bottom while there is something to save; focused fields
 * keep a margin above it (WCAG 2.4.11).
 */
export function DraftSaveBar() {
  const ctx = useRequiredDraftEdits();
  const pending = usePendingFields();
  const t = useT();
  const router = useRouter();
  const noteId = React.useId();
  const [note, setNote] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [failed, setFailed] = React.useState(false);
  const [conflict, setConflict] = React.useState<Conflict | null>(null);

  const keys = SECTION_ORDER.filter((k) => pending[k]);
  const mine = keys.flatMap((k) => [...(pending[k] ?? [])]);
  const sections = joinList(
    keys.map((k) => t(`agents.draft.section.${k}`)),
    t("agents.draft.bar.and"),
  );

  if (!ctx.canWrite || (!keys.length && !conflict)) return null;

  async function collect(): Promise<DraftPatch | null> {
    const parts = await Promise.all(keys.map((k) => ctx.store.handlers[k]?.collect() ?? Promise.resolve(null)));
    if (parts.some((p) => p === null)) {
      toast.error(t("agents.draft.bar.fix"));
      return null;
    }
    const patch: DraftPatch = Object.assign({}, ...parts);
    if (note.trim()) patch.note = note.trim();
    return patch;
  }

  async function send(revision: number, patch: DraftPatch, fields: string[]) {
    setSaving(true);
    setFailed(false);
    const res = await saveDraftAction({ ref: ctx.refId, agent: ctx.agentId, revision, patch });
    setSaving(false);
    if (res.ok) {
      setConflict(null);
      setNote("");
      ctx.adopt(res.data);
      toast.success(t("agents.draft.bar.saved", { n: res.data.number ?? "" }));
      router.refresh();
      return;
    }
    if (res.code === "revision_conflict" && res.info?.current) {
      setConflict({
        current: res.info.current as AgentDraft,
        changes: (res.info.changes as DraftChange[] | undefined) ?? [],
        patch,
        mine: fields,
      });
      return;
    }
    // An error of one section (an invalid phone…) is shown under its field.
    const shown = SECTION_ORDER.some((k) => ctx.store.handlers[k]?.onError?.(res) ?? false);
    setFailed(true);
    if (!shown) toast.error(actionErrorText(res, t));
  }

  async function save() {
    const patch = await collect();
    if (patch) await send(ctx.draft.revision, patch, mine);
  }

  /** What is on screen now — they may have kept typing while deciding —
   *  written on top of the newer draft. */
  async function keepMine() {
    if (!conflict) return;
    const patch = keys.length ? await collect() : conflict.patch;
    if (patch) await send(conflict.current.revision, patch, keys.length ? mine : conflict.mine);
  }

  function keepTheirs() {
    if (!conflict) return;
    const who = conflict.changes[conflict.changes.length - 1]?.by ?? "";
    ctx.adopt(conflict.current);
    setConflict(null);
    setNote("");
    setFailed(false);
    toast(t("agents.draft.conflict.keptTheirs", { who }));
    router.refresh();
  }

  function undo() {
    ctx.adopt(ctx.draft);
    setConflict(null);
    setNote("");
    setFailed(false);
  }

  return (
    <div
      role="region"
      aria-label={t("agents.draft.bar.region")}
      data-slot="draft-save-bar"
      className="sticky bottom-0 z-10 flex min-w-0 flex-col gap-2 pb-2"
    >
      <p className="sr-only" role="status">
        {keys.length ? t("agents.draft.bar.pending", { sections }) : ""}
      </p>
      {conflict ? (
        <DraftConflictNotice
          current={conflict.current}
          changes={conflict.changes}
          mine={conflict.mine}
          myPrompt={conflict.patch.system_prompt}
          busy={saving}
          onKeepMine={() => void keepMine()}
          onKeepTheirs={keepTheirs}
        />
      ) : null}
      {keys.length ? (
        <div className="flex min-w-0 flex-col gap-3 rounded-md border border-border bg-card p-3 text-sm shadow-sm md:flex-row md:items-end">
          <p className="inline-flex min-w-0 items-center gap-2 md:pb-2">
            <StatusDot tone={failed ? "danger" : "info"} pulse={saving} />
            <span className="min-w-0 text-pretty" data-slot="draft-save-summary">
              {t("agents.draft.bar.pending", { sections })}
            </span>
          </p>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <Label htmlFor={noteId} className="text-xs text-muted-foreground">
              {t("agents.draft.bar.note")}
            </Label>
            <Input
              id={noteId}
              value={note}
              maxLength={500}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t("agents.draft.bar.notePlaceholder")}
              autoComplete="off"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={undo} disabled={saving}>
              {t("agents.draft.bar.discard")}
            </Button>
            <Button onClick={() => void save()} loading={saving} disabled={conflict !== null}>
              {t("agents.draft.bar.save")}
            </Button>
          </div>
        </div>
      ) : null}
      {failed ? (
        <p role="alert" className="text-xs text-destructive">
          {t("agents.draft.bar.failed")}
        </p>
      ) : null}
    </div>
  );
}
