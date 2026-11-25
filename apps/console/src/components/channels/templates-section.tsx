"use client";

import { FileText, Pencil, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  canEditTemplate,
  draftFromComponents,
  languageLabel,
  type TemplateDraft,
} from "@nexus/ui";

import { deleteTemplateAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { TemplateEdited, TemplateList, TemplateRow } from "@/lib/backend/channels";

import { TemplateComposer, TemplateEditDialog, TemplatePreview, blockerText } from "./template-composer";
export { templateVariables } from "@nexus/ui";


const STATUS_TONE: Record<string, "positive" | "warning" | "danger" | "info" | "muted"> = {
  APPROVED: "positive",
  PENDING: "info",
  IN_APPEAL: "info",
  REJECTED: "danger",
  PAUSED: "warning",
  DISABLED: "danger",
  FLAGGED: "warning",
};
const KNOWN_STATUS = new Set(Object.keys(STATUS_TONE));

const QUALITY_TONE: Record<string, "positive" | "warning" | "danger"> = { GREEN: "positive", YELLOW: "warning", RED: "danger" };

/** Spec 050: Meta's quality score in words, toned; «—» when Meta has none yet. */
function qualityText(t: ReturnType<typeof useT>, score: string | null) {
  const key = (score ?? "").toUpperCase();
  const tone = QUALITY_TONE[key];
  if (!tone) return <span className="text-muted-foreground">—</span>;
  return <StatusBadge tone={tone}>{t(`builder.channel.account.quality.${key}` as "builder.channel.account.quality.GREEN")}</StatusBadge>;
}

const sameTemplate = (a: TemplateRow, b: TemplateRow) => a.name === b.name && a.language === b.language;

/**
 * Templates (HSM) of the client's number: state, quality, Meta's literal
 * rejection reason + suggested action; create (``TemplateComposer``), edit
 * (``TemplateEditDialog``, spec 075) and delete.
 * `list === null` means WhatsApp is not connected (409 upstream): the
 * section says so instead of erroring; `error` is a backend failure the
 * user can retry.
 */
export function TemplatesSection({
  refId,
  list,
  error,
  manage,
  onChanged,
  sectionId = "tpl",
  headingLevel = 2,
}: {
  refId: string;
  list: TemplateList | null;
  error: string | null;
  manage: boolean;
  /** For a screen that keeps the list in its own state (the number's page): reload after a change. */
  onChanged?: () => void;
  /** The anchor of the section (the number's page links to it from its index). */
  sectionId?: string;
  /** 3 inside the number's page, under the channel's own h2. */
  headingLevel?: 2 | 3;
}) {
  const t = useT();
  const router = useRouter();
  const Heading = headingLevel === 3 ? "h3" : "h2";
  const [createOpen, setCreateOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState<TemplateRow | null>(null);
  // QA 2026-10-30: a template opens to read all of it — what was sent, Meta's
  // whole reason — and «Duplicar y corregir» starts the composer from it.
  const [viewing, setViewing] = React.useState<TemplateRow | null>(null);
  const [draft, setDraft] = React.useState<{ key: number; value: TemplateDraft | null }>({ key: 0, value: null });
  // Spec 075: the template being edited, as it was when the editor opened —
  // its fingerprint is what the save sends, so a later list never swaps it
  // under the partner's feet. Only «Recargar» starts again from a fresh one.
  // `reloadFailures` counts the reloads whose list did not come back, so the editor can say so.
  const [editing, setEditing] = React.useState<{
    key: number;
    row: TemplateRow;
    open: boolean;
    reloading: boolean;
    reloadFailures: number;
  } | null>(null);
  // The spinner on «Recargar» follows the refresh itself: a transition always
  // ends, so it cannot stay stuck when the list comes back unchanged.
  const [refreshing, startRefresh] = React.useTransition();

  function openComposer(value: TemplateDraft | null) {
    setDraft((d) => ({ key: d.key + 1, value }));
    setViewing(null);
    setCreateOpen(true);
  }
  const [pending, startTransition] = React.useTransition();

  function refresh() {
    router.refresh();
    onChanged?.();
  }

  function openEditor(row: TemplateRow) {
    setViewing(null);
    setEditing((e) => ({ key: (e?.key ?? 0) + 1, row, open: true, reloading: false, reloadFailures: 0 }));
  }

  function closeEditor() {
    setEditing((e) => (e ? { ...e, open: false, reloading: false } : e));
  }

  function saved(result: TemplateEdited) {
    if (result.changed) {
      const st = (result.status ?? "").toUpperCase();
      const statusKey = (KNOWN_STATUS.has(st) ? `tpl.status.${st}` : "tpl.status.unknown") as "tpl.status.APPROVED";
      toast.success(t("tpl.edited", { status: t(statusKey) }));
    } else {
      toast.success(t("tpl.edit.unchanged"));
    }
    closeEditor();
    refresh();
  }

  function reloadEditing() {
    setEditing((e) => (e ? { ...e, reloading: true } : e));
    startRefresh(() => refresh());
  }

  // After «Recargar», the list comes back with the template as it is now: the
  // editor starts again from it, or closes and shows why if it can no longer be
  // edited. Adjusted while rendering, when the list changes (no effect needed).
  const [seenList, setSeenList] = React.useState(list);
  // The template was gone when the list came back: said once, after rendering.
  const [gone, setGone] = React.useState<{ message: string } | null>(null);
  if (list !== seenList) {
    setSeenList(list);
    if (editing?.open && editing.reloading && !list) {
      // The list did not come back (backend error, WhatsApp disconnected): the editor says it.
      setEditing({ ...editing, reloading: false, reloadFailures: editing.reloadFailures + 1 });
    } else if (editing?.open && editing.reloading && list) {
      const fresh = list.items.find((r) => sameTemplate(r, editing.row));
      if (fresh && canEditTemplate(fresh)) {
        setEditing({ key: editing.key + 1, row: fresh, open: true, reloading: false, reloadFailures: 0 });
      } else {
        setEditing({ ...editing, open: false, reloading: false });
        if (fresh) setViewing(fresh);
        else setGone({ message: t("tpl.edit.gone") });
      }
    }
  }
  React.useEffect(() => {
    if (gone) toast.error(gone.message);
  }, [gone]);

  function remove(name: string) {
    startTransition(async () => {
      const res = await deleteTemplateAction({ ref: refId, name });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("tpl.deleted"));
      setDeleting(null);
      router.refresh();
      onChanged?.();
    });
  }

  return (
    <section id={sectionId} className="flex min-w-0 scroll-mt-24 flex-col gap-3" aria-labelledby={`${sectionId}-title`} aria-busy={pending}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <Heading id={`${sectionId}-title`} className="text-base font-medium">
            {t("tpl.title")}
          </Heading>
          <p className=" text-sm text-muted-foreground">{t("tpl.description")}</p>
        </div>
        {manage && list ? <Button onClick={() => openComposer(null)}>{t("tpl.new")}</Button> : null}
      </div>
      {list === null && !error ? (
        <p className="rounded-md bg-muted px-4 py-3 text-sm text-muted-foreground">{t("tpl.notConnected")}</p>
      ) : error ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-status-danger-border px-4 py-3 text-sm">
          <span className="min-w-0 break-words text-pretty">{error}</span>
          <Button variant="outline" size="sm" onClick={() => (onChanged ? onChanged() : router.refresh())}>
            {t("common.retry")}
          </Button>
        </div>
      ) : list && list.items.length === 0 ? (
        <EmptyState icon={FileText} title={t("tpl.empty")} action={manage ? <Button onClick={() => openComposer(null)}>{t("tpl.new")}</Button> : undefined} readonly={!manage} />
      ) : list ? (
        <>
          <p className="text-xs text-muted-foreground tabular-nums">{t("tpl.counts", { approved: list.approved, rejected: list.rejected, pending: list.pending })}</p>
          <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("tpl.col.name")}</TableHead>
                  <TableHead>{t("tpl.col.language")}</TableHead>
                  <TableHead>{t("tpl.col.category")}</TableHead>
                  <TableHead>{t("tpl.col.status")}</TableHead>
                  <TableHead>{t("tpl.col.quality")}</TableHead>
                  <TableHead>{t("tpl.col.reason")}</TableHead>
                  <TableHead>{t("tpl.col.action")}</TableHead>
                  {manage ? <TableHead className="text-right">{t("common.actions")}</TableHead> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.items.map((row) => {
                  const st = (row.status ?? "").toUpperCase();
                  const statusKey = (KNOWN_STATUS.has(st) ? `tpl.status.${st}` : "tpl.status.unknown") as "tpl.status.APPROVED";
                  return (
                    <TableRow key={`${row.name}:${row.language}`}>
                      <TableCell className="max-w-56">
                        <button
                          type="button"
                          className="block max-w-full cursor-pointer truncate text-left font-mono text-xs text-primary-text underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                          onClick={() => setViewing(row)}
                        >
                          {row.name}
                        </button>
                      </TableCell>
                      <TableCell className="text-xs">{languageLabel(row.language)}</TableCell>
                      <TableCell>
                        <span className="grid gap-1">
                          <span>{row.category ? t(`tpl.category.${row.category}` as "tpl.category.UTILITY") : "—"}</span>
                          {row.pending_category ? (
                            <span className="text-xs text-status-warning-text" data-slot="pending-category">
                              {t("tpl.category.pending", { category: t(`tpl.category.${row.pending_category}` as "tpl.category.UTILITY") })}
                            </span>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell>
                        <StatusBadge tone={STATUS_TONE[st] ?? "muted"}>{t(statusKey)}</StatusBadge>
                      </TableCell>
                      <TableCell>{qualityText(t, row.quality_score)}</TableCell>
                      <TableCell className="max-w-72">
                        {row.rejection_reason ? (
                          <span className="block truncate font-mono text-xs" title={row.rejection_reason}>
                            {row.rejection_reason}
                          </span>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="max-w-80 text-xs text-pretty">{t(`tpl.action.${row.suggested_action}` as "tpl.action.none")}</TableCell>
                      {manage ? (
                        <TableCell className="text-right">
                          <span className="inline-flex items-center gap-1">
                            {canEditTemplate(row) ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openEditor(row)}
                                aria-label={`${t("tpl.edit")}: ${row.name} (${languageLabel(row.language)})`}
                              >
                                <Pencil aria-hidden="true" />
                              </Button>
                            ) : null}
                            <Button variant="ghost" size="sm" onClick={() => setDeleting(row)} aria-label={`${t("tpl.delete")}: ${row.name}`}>
                              <Trash2 aria-hidden="true" />
                            </Button>
                          </span>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </>
      ) : null}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("tpl.delete")}
        description={deleting ? t("tpl.delete.confirm", { name: deleting.name }) : undefined}
        confirmLabel={t("tpl.delete")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={() => (deleting ? remove(deleting.name) : undefined)}
      />
      <TemplateDetail
        row={viewing}
        manage={manage}
        onClose={() => setViewing(null)}
        onDuplicate={manage ? (row) => openComposer(draftFromComponents(row)) : undefined}
        onEdit={manage ? openEditor : undefined}
      />
      <TemplateComposer key={draft.key} refId={refId} open={createOpen} onOpenChange={setCreateOpen} onCreated={onChanged} initial={draft.value} />
      {editing ? (
        <TemplateEditDialog
          key={editing.key}
          refId={refId}
          row={editing.row}
          open={editing.open}
          onClose={closeEditor}
          onSaved={saved}
          onReload={reloadEditing}
          reloading={editing.reloading && refreshing}
          reloadFailures={editing.reloadFailures}
        />
      ) : null}
    </section>
  );
}

/** One template, read whole: the message as sent, Meta's full reason and what to do. */
function TemplateDetail({
  row,
  manage,
  onClose,
  onDuplicate,
  onEdit,
}: {
  row: TemplateRow | null;
  manage: boolean;
  onClose: () => void;
  onDuplicate?: (row: TemplateRow) => void;
  onEdit?: (row: TemplateRow) => void;
}) {
  const t = useT();
  const draft = row ? draftFromComponents(row) : null;
  const st = (row?.status ?? "").toUpperCase();
  const statusKey = (KNOWN_STATUS.has(st) ? `tpl.status.${st}` : "tpl.status.unknown") as "tpl.status.APPROVED";
  return (
    <Dialog open={row !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-mono text-base break-all">{row?.name}</DialogTitle>
          <DialogDescription>
            {row ? `${languageLabel(row.language)} · ${row.category ? t(`tpl.category.${row.category}` as "tpl.category.UTILITY") : "—"}` : null}
          </DialogDescription>
        </DialogHeader>
        {row ? (
          <div className="grid min-w-0 gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={STATUS_TONE[st] ?? "muted"}>{t(statusKey)}</StatusBadge>
            </div>
            {row.rejection_reason ? (
              <div className="grid gap-1 rounded-md border border-status-danger-border p-3 text-sm" data-slot="rejection">
                <p className="font-medium">{t("tpl.col.reason")}</p>
                <p className="break-words font-mono text-xs">{row.rejection_reason}</p>
                <p className="text-pretty text-muted-foreground">{t(`tpl.action.${row.suggested_action}` as "tpl.action.none")}</p>
              </div>
            ) : null}
            {manage && row.edit_blocker ? (
              // 3.2 · One line: which part keeps it out, and where it is edited.
              <p className="text-pretty text-muted-foreground" data-slot="edit-blocker">
                {blockerText(t, row.edit_blocker)}
              </p>
            ) : null}
            {draft ? (
              <div role="group" className="grid gap-2" aria-label={t("tpl.compose.preview")}>
                <p className="text-sm font-medium">{t("tpl.compose.preview")}</p>
                <TemplatePreview header={draft.header} body={draft.body} footer={draft.footer} buttons={draft.buttons} examples={draft.examples} />
              </div>
            ) : null}
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.close")}
          </Button>
          {row && onDuplicate ? (
            <Button variant={row && onEdit && canEditTemplate(row) ? "outline" : "default"} onClick={() => onDuplicate(row)}>
              {t("tpl.duplicate")}
            </Button>
          ) : null}
          {row && onEdit && canEditTemplate(row) ? <Button onClick={() => onEdit(row)}>{t("tpl.edit")}</Button> : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
