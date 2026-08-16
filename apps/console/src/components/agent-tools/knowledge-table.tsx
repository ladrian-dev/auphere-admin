"use client";

import { BookOpen, RefreshCw, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ConfirmDialog,
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
  formatBytes,
  formatDateTime,
  formatNumber,
} from "@nexus/ui";

import { addKnowledgeUrlAction, deleteKnowledgeAction, reindexKnowledgeAction, uploadKnowledgeAction } from "@/app/(console)/clients/[ref]/knowledge/actions";
import { useLocale, useT } from "@/i18n/client";
import { KNOWLEDGE_MAX_UPLOAD_BYTES, type KnowledgeDocumentOut, type KnowledgeListOut } from "@/lib/backend/agent-tools-types";

import { knowledgeErrorKey, knowledgeStatusTone, knowledgeUsageRatio, usageWidthClass } from "./lib";

type Props = { refId: string; data: KnowledgeListOut; canWrite: boolean };

const ACCEPT = ".pdf,.txt,.md,.html,.htm,application/pdf,text/plain,text/markdown,text/html";

/**
 * Knowledge (CP-15): upload + URL forms, prompt-budget meter and the
 * document table (metadata only). Delete asks; reindex is one click.
 */
export function KnowledgeTable({ refId, data, canWrite }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [deleting, setDeleting] = React.useState<KnowledgeDocumentOut | null>(null);
  const [pending, startTransition] = React.useTransition();
  const ratio = knowledgeUsageRatio(data.indexed_chars, data.prompt_char_cap);
  const over = data.indexed_chars > data.prompt_char_cap && data.prompt_char_cap > 0;

  function reindex(doc: KnowledgeDocumentOut) {
    startTransition(async () => {
      const res = await reindexKnowledgeAction({ ref: refId, id: doc.id });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("knowledge.reindexed", { title: doc.title }));
      router.refresh();
    });
  }
  async function confirmDelete() {
    if (!deleting) return;
    const doc = deleting;
    const res = await deleteKnowledgeAction({ ref: refId, id: doc.id });
    if (!res.ok) return void toast.error(res.message);
    toast.success(t("knowledge.deleted", { title: doc.title }));
    setDeleting(null);
    router.refresh();
  }

  const forms = canWrite ? (
    <div className="grid gap-3 md:grid-cols-2">
      <UploadForm refId={refId} />
      <UrlForm refId={refId} />
    </div>
  ) : null;

  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
      {!canWrite ? <p className="text-xs text-muted-foreground">{t("knowledge.readonly")}</p> : null}
      {forms}

      <div className="flex min-w-0 flex-col gap-1" role="group" aria-label={t("knowledge.usage.label")}>
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground tabular-nums">
          <span>{t("knowledge.usage", { used: formatNumber(data.indexed_chars, locale), cap: formatNumber(data.prompt_char_cap, locale) })}</span>
          <span>{formatNumber(ratio, locale, { style: "percent", maximumFractionDigits: 0 })}</span>
        </div>
        <div
          role="progressbar"
          aria-label={t("knowledge.usage.label")}
          aria-valuemin={0}
          aria-valuemax={data.prompt_char_cap}
          aria-valuenow={Math.min(data.indexed_chars, data.prompt_char_cap)}
          className="h-2 w-full overflow-hidden rounded-full bg-muted"
        >
          <div className={["h-full rounded-full transition-[width]", usageWidthClass(ratio), over ? "bg-status-danger" : ratio > 0.8 ? "bg-status-warning" : "bg-primary"].join(" ")} />
        </div>
        {over ? <p className="text-xs text-status-danger">{t("knowledge.usage.over")}</p> : null}
      </div>

      {data.items.length === 0 ? (
        <EmptyState icon={BookOpen} title={t("knowledge.empty.title")} description={t("knowledge.empty.body")} readonly />
      ) : (
        <div className="overflow-x-auto rounded-md bg-card ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("knowledge.col.title")}</TableHead>
                <TableHead>{t("knowledge.col.kind")}</TableHead>
                <TableHead>{t("common.status")}</TableHead>
                <TableHead className="text-right">{t("knowledge.col.size")}</TableHead>
                <TableHead className="text-right">{t("knowledge.col.chunks")}</TableHead>
                <TableHead>{t("knowledge.col.indexed")}</TableHead>
                {canWrite ? <TableHead className="text-right">{t("common.actions")}</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="max-w-64">
                    <div className="flex min-w-0 flex-col">
                      <span className="min-w-0 truncate font-medium" title={doc.title}>
                        {doc.title}
                      </span>
                      {doc.source_url ? (
                        <a href={doc.source_url} target="_blank" rel="noopener noreferrer" className="min-w-0 truncate font-mono text-xs text-muted-foreground underline-offset-4 hover:underline" title={doc.source_url}>
                          {doc.source_url}
                        </a>
                      ) : (
                        <span className="min-w-0 truncate font-mono text-xs text-muted-foreground" title={doc.mime}>
                          {doc.mime}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>{t(`knowledge.kind.${doc.kind}`)}</TableCell>
                  <TableCell>
                    <div className="flex min-w-0 flex-col gap-1">
                      <StatusBadge tone={knowledgeStatusTone(doc.status)} pulse={doc.status === "pending"}>
                        {t(`knowledge.status.${doc.status}`)}
                      </StatusBadge>
                      {doc.status === "failed" ? <span className="max-w-64 text-xs text-pretty text-status-danger">{t(knowledgeErrorKey(doc.error_code))}</span> : null}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatBytes(doc.size_bytes, locale)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(doc.chunk_count, locale)}</TableCell>
                  <TableCell className="tabular-nums">{formatDateTime(doc.indexed_at, locale)}</TableCell>
                  {canWrite ? (
                    <TableCell className="text-right">
                      <span className="inline-flex gap-1">
                        <Button size="icon-sm" variant="ghost" onClick={() => reindex(doc)} disabled={pending} aria-label={`${t("knowledge.reindex")} · ${doc.title}`} title={t("knowledge.reindex")}>
                          <RefreshCw aria-hidden="true" />
                        </Button>
                        <Button size="icon-sm" variant="ghost" onClick={() => setDeleting(doc)} disabled={pending} aria-label={`${t("knowledge.delete")} · ${doc.title}`} title={t("knowledge.delete")}>
                          <Trash2 aria-hidden="true" />
                        </Button>
                      </span>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("knowledge.delete.title", { title: deleting?.title ?? "" })}
        description={t("knowledge.delete.body")}
        confirmLabel={t("knowledge.delete")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={confirmDelete}
      />
    </div>
  );
}

function UploadForm({ refId }: { refId: string }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [error, setError] = React.useState<string | null>(null);
  const formRef = React.useRef<HTMLFormElement>(null);

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const file = fd.get("file");
    if (!(file instanceof File) || file.size === 0) return void setError(t("knowledge.upload.noFile"));
    if (file.size > KNOWLEDGE_MAX_UPLOAD_BYTES) return void setError(t("knowledge.upload.tooLarge"));
    setError(null);
    fd.set("ref", refId);
    startTransition(async () => {
      const res = await uploadKnowledgeAction(fd);
      if (!res.ok) return void toast.error(res.status === 413 ? t("knowledge.upload.tooLarge") : res.message);
      toast.success(t("knowledge.upload.done", { title: res.data.title }));
      formRef.current?.reset();
      router.refresh();
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("knowledge.upload.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form ref={formRef} onSubmit={submit} className="grid gap-3" aria-busy={pending} noValidate>
          <div className="grid gap-1">
            <Label htmlFor="kn-file">{t("knowledge.upload.file")}</Label>
            <Input id="kn-file" name="file" type="file" accept={ACCEPT} required aria-invalid={error ? true : undefined} aria-describedby={error ? "kn-file-err" : undefined} />
            {error ? (
              <p id="kn-file-err" className="text-xs text-destructive" aria-live="polite">
                {error}
              </p>
            ) : null}
          </div>
          <div className="grid gap-1">
            <Label htmlFor="kn-title">{t("knowledge.upload.titleField")}</Label>
            <Input id="kn-title" name="title" maxLength={255} autoComplete="off" />
          </div>
          <div>
            <Button type="submit" size="sm" disabled={pending}>
              {t("knowledge.upload.submit")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function UrlForm({ refId }: { refId: string }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [url, setUrl] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!/^https?:\/\/\S{3,}$/.test(url.trim())) return void setError(t("knowledge.url.invalid"));
    setError(null);
    startTransition(async () => {
      const res = await addKnowledgeUrlAction({ ref: refId, url: url.trim(), title: title.trim() || undefined });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("knowledge.url.done", { title: res.data.title }));
      setUrl("");
      setTitle("");
      router.refresh();
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("knowledge.url.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3" aria-busy={pending} noValidate>
          <div className="grid gap-1">
            <Label htmlFor="kn-url">{t("knowledge.url.field")}</Label>
            <Input id="kn-url" type="url" inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} maxLength={2048} placeholder="https://" spellCheck={false} autoComplete="off" aria-invalid={error ? true : undefined} aria-describedby={error ? "kn-url-err" : undefined} />
            {error ? (
              <p id="kn-url-err" className="text-xs text-destructive" aria-live="polite">
                {error}
              </p>
            ) : null}
          </div>
          <div className="grid gap-1">
            <Label htmlFor="kn-url-title">{t("knowledge.upload.titleField")}</Label>
            <Input id="kn-url-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} autoComplete="off" />
          </div>
          <div>
            <Button type="submit" size="sm" disabled={pending}>
              {t("knowledge.url.submit")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
