"use client";

import { FileText, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  ConfirmDialog,
  EmptyState,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";

import { deleteTemplateAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { TemplateList, TemplateRow } from "@/lib/backend/channels";

import { TemplateComposer } from "./template-composer";
export { templateVariables } from "./template-rules";


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

/**
 * Templates (HSM) of the client's number: state, quality, Meta's literal
 * rejection reason + suggested action; create (``TemplateComposer``) and delete.
 * `list === null` means WhatsApp is not connected (409 upstream): the
 * section says so instead of erroring; `error` is a backend failure the
 * user can retry.
 */
export function TemplatesSection({ refId, list, error, manage }: { refId: string; list: TemplateList | null; error: string | null; manage: boolean }) {
  const t = useT();
  const router = useRouter();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState<TemplateRow | null>(null);
  const [pending, startTransition] = React.useTransition();

  function remove(name: string) {
    startTransition(async () => {
      const res = await deleteTemplateAction({ ref: refId, name });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("tpl.deleted"));
      setDeleting(null);
      router.refresh();
    });
  }

  return (
    <section className="flex min-w-0 flex-col gap-3" aria-labelledby="tpl-title" aria-busy={pending}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="tpl-title" className="text-base font-medium">
            {t("tpl.title")}
          </h2>
          <p className=" text-sm text-muted-foreground">{t("tpl.description")}</p>
        </div>
        {manage && list ? <Button onClick={() => setCreateOpen(true)}>{t("tpl.new")}</Button> : null}
      </div>
      {list === null && !error ? (
        <p className="rounded-md bg-muted px-4 py-3 text-sm text-muted-foreground">{t("tpl.notConnected")}</p>
      ) : error ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-status-danger/40 px-4 py-3 text-sm">
          <span className="min-w-0 truncate" title={error}>
            {error}
          </span>
          <Button variant="outline" size="sm" onClick={() => router.refresh()}>
            {t("common.retry")}
          </Button>
        </div>
      ) : list && list.items.length === 0 ? (
        <EmptyState icon={FileText} title={t("tpl.empty")} action={manage ? <Button onClick={() => setCreateOpen(true)}>{t("tpl.new")}</Button> : undefined} readonly={!manage} />
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
                      <TableCell className="max-w-56 truncate font-mono text-xs" title={row.name}>
                        {row.name}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.language}</TableCell>
                      <TableCell>{row.category ? t(`tpl.category.${row.category}` as "tpl.category.UTILITY") : "—"}</TableCell>
                      <TableCell>
                        <StatusBadge tone={STATUS_TONE[st] ?? "muted"}>{t(statusKey)}</StatusBadge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.quality_score ?? "—"}</TableCell>
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
                          <Button variant="ghost" size="sm" onClick={() => setDeleting(row)} aria-label={`${t("tpl.delete")}: ${row.name}`}>
                            <Trash2 aria-hidden="true" />
                          </Button>
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
      <TemplateComposer refId={refId} open={createOpen} onOpenChange={setCreateOpen} />
    </section>
  );
}
