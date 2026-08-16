"use client";

import { FileText, Trash2 } from "lucide-react";
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
  Input,
  Label,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
} from "@nexus/ui";

import { createTemplateAction, deleteTemplateAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { TemplateButton, TemplateList, TemplateRow } from "@/lib/backend/channels";

import { SELECT_CLASS } from "./whatsapp-connect";

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
const NAME_RE = /^[a-z0-9_]{1,512}$/;

/**
 * Templates (HSM) of the client's number: state, quality, Meta's literal
 * rejection reason + suggested action; create (minimal form) and delete.
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
          <p className="max-w-prose text-sm text-muted-foreground">{t("tpl.description")}</p>
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
      <CreateTemplateDialog refId={refId} open={createOpen} onOpenChange={setCreateOpen} />
    </section>
  );
}

type ButtonDraft = TemplateButton;

function CreateTemplateDialog({ refId, open, onOpenChange }: { refId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [name, setName] = React.useState("");
  const [language, setLanguage] = React.useState("es");
  const [category, setCategory] = React.useState<"MARKETING" | "UTILITY" | "AUTHENTICATION">("UTILITY");
  const [header, setHeader] = React.useState("");
  const [body, setBody] = React.useState("");
  const [footer, setFooter] = React.useState("");
  const [buttons, setButtons] = React.useState<ButtonDraft[]>([]);
  const nameInvalid = name.length > 0 && !NAME_RE.test(name);
  const valid = NAME_RE.test(name) && body.trim().length > 0 && buttons.every((b) => b.label.trim().length > 0);

  function submit() {
    startTransition(async () => {
      const res = await createTemplateAction({
        ref: refId,
        name,
        language,
        category,
        header_text: header || undefined,
        body_text: body,
        footer_text: footer || undefined,
        buttons: buttons.map((b) => ({ ...b, url: b.url || undefined, phone_number: b.phone_number || undefined })),
      });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("tpl.created"));
      onOpenChange(false);
      setName("");
      setBody("");
      setHeader("");
      setFooter("");
      setButtons([]);
      router.refresh();
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("tpl.new")}</DialogTitle>
          <DialogDescription>{t("tpl.form.body.help")}</DialogDescription>
        </DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) submit();
          }}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor="tpl-name">{t("tpl.form.name")}</Label>
            <Input id="tpl-name" value={name} onChange={(e) => setName(e.target.value)} aria-invalid={nameInvalid} className="font-mono" required />
            {nameInvalid ? (
              <p className="text-xs text-destructive" role="alert">
                {t("tpl.form.invalidName")}
              </p>
            ) : null}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="tpl-lang">{t("tpl.form.language")}</Label>
              <Input id="tpl-lang" value={language} onChange={(e) => setLanguage(e.target.value)} className="font-mono" />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="tpl-cat">{t("tpl.form.category")}</Label>
              <select id="tpl-cat" className={SELECT_CLASS} value={category} onChange={(e) => setCategory(e.target.value as typeof category)}>
                {(["UTILITY", "MARKETING", "AUTHENTICATION"] as const).map((c) => (
                  <option key={c} value={c}>
                    {t(`tpl.category.${c}` as "tpl.category.UTILITY")}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="tpl-header">{t("tpl.form.header")}</Label>
            <Input id="tpl-header" value={header} onChange={(e) => setHeader(e.target.value)} maxLength={60} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="tpl-body">{t("tpl.form.body")}</Label>
            <Textarea id="tpl-body" value={body} onChange={(e) => setBody(e.target.value)} maxLength={1024} rows={5} required />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="tpl-footer">{t("tpl.form.footer")}</Label>
            <Input id="tpl-footer" value={footer} onChange={(e) => setFooter(e.target.value)} maxLength={60} />
          </div>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">{t("tpl.form.buttons")}</legend>
            {buttons.map((b, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[auto_1fr_1fr_auto]">
                <select
                  className={SELECT_CLASS}
                  value={b.type}
                  aria-label={t("tpl.form.buttons")}
                  onChange={(e) => setButtons((prev) => prev.map((x, j) => (j === i ? { ...x, type: e.target.value as ButtonDraft["type"] } : x)))}
                >
                  {(["QUICK_REPLY", "URL", "PHONE_NUMBER"] as const).map((k) => (
                    <option key={k} value={k}>
                      {t(`tpl.form.button.${k}` as "tpl.form.button.URL")}
                    </option>
                  ))}
                </select>
                <Input
                  aria-label={t("tpl.form.button.label")}
                  placeholder={t("tpl.form.button.label")}
                  value={b.label}
                  maxLength={25}
                  onChange={(e) => setButtons((prev) => prev.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
                />
                {b.type === "URL" ? (
                  <Input aria-label="URL" placeholder="https://" value={b.url ?? ""} onChange={(e) => setButtons((prev) => prev.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} />
                ) : b.type === "PHONE_NUMBER" ? (
                  <Input aria-label="E.164" placeholder="+34…" value={b.phone_number ?? ""} onChange={(e) => setButtons((prev) => prev.map((x, j) => (j === i ? { ...x, phone_number: e.target.value } : x)))} />
                ) : (
                  <span />
                )}
                <Button type="button" variant="ghost" size="sm" onClick={() => setButtons((prev) => prev.filter((_, j) => j !== i))} aria-label={t("common.cancel")}>
                  <Trash2 aria-hidden="true" />
                </Button>
              </div>
            ))}
            {buttons.length < 3 ? (
              <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setButtons((prev) => [...prev, { type: "QUICK_REPLY", label: "" }])}>
                {t("tpl.form.button.add")}
              </Button>
            ) : null}
          </fieldset>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={pending || !valid} aria-busy={pending}>
              {t("tpl.form.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
