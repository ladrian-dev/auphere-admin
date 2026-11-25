"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  TemplateEditor,
  TemplatePreview as SharedTemplatePreview,
  draftFromContent,
  templateEditFailure,
  type ButtonDraft,
  type TemplateDraft,
  type TemplateEditFailure,
  type TemplateEditorOutcome,
  type TemplateSubmission,
} from "@nexus/ui";

import { createTemplateAction, editTemplateAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import { TEMPLATE_BLOCKERS, type TemplateEdited, type TemplateRow } from "@/lib/backend/channels";

import { useTemplateEditorLabels } from "./template-editor-labels";

/**
 * The WhatsApp template composer (spec 025 follow-up, 2026-10-01).
 *
 * Spec 075 (R9): the editor itself lives in `@nexus/ui` as `TemplateEditor`,
 * shared with the operator panel. This is the console's shell around it: the
 * dialog, the words in the partner's language, the Server Action and what
 * happens after Meta answers.
 */
export function TemplateComposer({
  refId,
  open,
  onOpenChange,
  onCreated,
  initial = null,
}: {
  refId: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  /** For a screen that keeps the list in its own state (the number's page). */
  onCreated?: () => void;
  /** «Duplicar y corregir»: start from a template Meta rejected. Read once (remount with a key to change it). */
  initial?: TemplateDraft | null;
}) {
  const t = useT();
  const router = useRouter();
  const labels = useTemplateEditorLabels("create");
  const [busy, setBusy] = React.useState(false);
  const [serverError, setServerError] = React.useState<string | null>(null);
  // A new editor after a template is created: the next one starts empty.
  const [generation, setGeneration] = React.useState(0);

  async function create(draft: TemplateSubmission): Promise<TemplateEditorOutcome> {
    setServerError(null);
    setBusy(true);
    try {
      const res = await createTemplateAction({ ref: refId, ...draft });
      if (!res.ok) {
        setServerError(res.message);
        return { kind: "failed" };
      }
      toast.success(t("tpl.created"));
      setGeneration((g) => g + 1);
      onOpenChange(false);
      router.refresh();
      onCreated?.();
      return { kind: "done" };
    } catch {
      // The action itself failed (network, a refused input): say it instead of staying silent.
      setServerError(t("tpl.edit.failed"));
      return { kind: "failed" };
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>{t("tpl.new")}</DialogTitle>
          <DialogDescription>{t("tpl.compose.intro")}</DialogDescription>
        </DialogHeader>
        <TemplateEditor
          key={generation}
          mode="create"
          initial={initial}
          labels={labels}
          pending={busy}
          serverError={serverError}
          onSubmit={create}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

/** The sentence for a failed edit (spec 075): Meta's own words when it gave them, ours otherwise. */
function editFailureText(t: ReturnType<typeof useT>, failure: TemplateEditFailure): string {
  switch (failure.kind) {
    case "template_changed":
      return t("tpl.edit.changed");
    case "template_not_found":
      return t("tpl.edit.not_found");
    case "not_editable":
      return blockerText(t, failure.blocker);
    case "category_locked":
      return t("tpl.edit.category_locked");
    case "missing_examples":
      return t("tpl.edit.missing_examples", { list: failure.variables.map((v) => `{{${v}}}`).join(", ") });
    case "system_variables":
      return [
        failure.missing.length ? t("tpl.system.missing", { list: failure.missing.map((v) => `{{${v}}}`).join(", ") }) : null,
        failure.extra.length ? t("tpl.system.extra", { list: failure.extra.map((v) => `{{${v}}}`).join(", ") }) : null,
      ]
        .filter(Boolean)
        .join(" ");
    case "meta_rejected":
      // The edit limit of an approved template has no code we have seen (research R2, C2):
      // Meta's own sentence says it, as it says any other refusal.
      return failure.userMessage ? t("tpl.edit.meta_rejected.with", { message: failure.userMessage }) : t("tpl.edit.meta_rejected");
    case "whatsapp_not_connected":
      return t("tpl.notConnected");
    case "forbidden":
      return t("ch.forbidden.write");
    default:
      return t("tpl.edit.failed");
  }
}

/** Spec 075 (3.2): why a template cannot be edited here, in one sentence. */
export function blockerText(t: ReturnType<typeof useT>, blocker: string | null | undefined): string {
  const key = `tpl.blocker.${blocker ?? "unknown"}`;
  return (TEMPLATE_BLOCKERS as readonly string[]).includes(blocker ?? "") ? t(key as MessageKey) : t("tpl.blocker.unknown");
}

/**
 * Spec 075: edit one language of a template, keeping its name. The editor
 * starts from what the API split (`row.draft`) and saves with the fingerprint
 * the list gave (`row.version`): if the template changed meanwhile, the API
 * refuses and this offers to reload instead of overwriting (7.1).
 */
export function TemplateEditDialog({
  refId,
  row,
  open,
  onClose,
  onSaved,
  onReload,
  reloading = false,
  reloadFailures = 0,
}: {
  refId: string;
  /** The template as it was when the editor opened. Remount with a key to start from another. */
  row: TemplateRow;
  open: boolean;
  onClose: () => void;
  onSaved: (result: TemplateEdited) => void;
  /** Ask for the list again; the caller reopens the editor with the fresh template. */
  onReload: () => void;
  /** The list is on its way back after «Recargar». */
  reloading?: boolean;
  /** Goes up each time «Recargar» did not bring the list back: the editor says so. */
  reloadFailures?: number;
}) {
  const t = useT();
  const labels = useTemplateEditorLabels("edit");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<{ text: string; reload: boolean } | null>(null);
  // A failed reload is said where the partner is looking, not in the list behind the dialog.
  const [seenFailures, setSeenFailures] = React.useState(reloadFailures);
  if (reloadFailures !== seenFailures) {
    setSeenFailures(reloadFailures);
    setError({ text: t("tpl.edit.reload_failed"), reload: true });
  }
  const locked = (row.status ?? "").toUpperCase() === "APPROVED";
  const initial = React.useMemo(() => (row.draft ? draftFromContent(row.name, row.language, row.draft) : null), [row]);

  async function save(draft: TemplateSubmission, { confirm }: { confirm: boolean }): Promise<TemplateEditorOutcome> {
    // The editor does not offer Authentication when editing (1.4, 3.2): nothing to send.
    if (draft.category === "AUTHENTICATION") return { kind: "failed" };
    setError(null);
    setBusy(true);
    try {
      // The name and the language are the template's, in the path: never in the body.
      const res = await editTemplateAction({
        ref: refId,
        name: row.name,
        language: row.language,
        version: row.version,
        confirm,
        ...(locked ? {} : { category: draft.category }),
        header_text: draft.header_text,
        body_text: draft.body_text,
        footer_text: draft.footer_text,
        buttons: draft.buttons,
        examples: draft.examples,
      });
      if (res.ok) {
        onSaved(res.data);
        return { kind: "done" };
      }
      const failure = templateEditFailure(res.code, res.info, res.status);
      if (failure.kind === "confirmation_required") return failure;
      setError({
        text: editFailureText(t, failure),
        reload: failure.kind === "template_changed" || failure.kind === "not_editable" || failure.kind === "template_not_found",
      });
      return failure.kind === "system_variables" ? failure : { kind: "failed" };
    } catch {
      // The action itself failed (network, a refused input): what was written stays.
      setError({ text: t("tpl.edit.failed"), reload: false });
      return { kind: "failed" };
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>{t("tpl.edit.title")}</DialogTitle>
          <DialogDescription>{t("tpl.edit.intro")}</DialogDescription>
        </DialogHeader>
        {row.rejection_reason ? (
          // 1.2 · What Meta said and what to fix, in sight while editing.
          <div className="grid min-w-0 gap-1 rounded-md border border-status-danger-border p-3 text-sm" data-slot="rejection">
            <p className="font-medium">{t("tpl.col.reason")}</p>
            <p className="break-words font-mono text-xs">{row.rejection_reason}</p>
            <p className="text-pretty text-muted-foreground">{t(`tpl.action.${row.suggested_action}` as MessageKey)}</p>
          </div>
        ) : null}
        <TemplateEditor
          mode="edit"
          initial={initial}
          categoryLocked={locked}
          systemVariables={row.system_variables ?? null}
          labels={labels}
          pending={busy}
          serverError={error?.text}
          serverErrorAction={
            error?.reload ? (
              <Button type="button" variant="outline" size="sm" onClick={onReload} loading={reloading}>
                {t("tpl.edit.reload")}
              </Button>
            ) : undefined
          }
          onSubmit={save}
          onCancel={onClose}
        />
      </DialogContent>
    </Dialog>
  );
}

/** The message as WhatsApp shows it, with the examples in place of the variables. */
export function TemplatePreview(props: {
  header: string;
  body: string;
  footer: string;
  buttons: ButtonDraft[];
  examples: Record<string, string>;
}) {
  const t = useT();
  return <SharedTemplatePreview {...props} emptyLabel={t("tpl.compose.preview.empty")} />;
}
