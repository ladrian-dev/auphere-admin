"use client";

import { BookOpen, RefreshCw, Trash2, Upload } from "lucide-react";
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
  Meter,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  buttonVariants,
  cn,
  formatBytes,
  formatDateTime,
  formatNumber,
} from "@nexus/ui";

import {
  addKnowledgeUrlAction,
  deleteKnowledgeAction,
  reindexKnowledgeAction,
  restoreKnowledgeAction,
  uploadKnowledgeAction,
} from "@/app/(console)/clients/[ref]/knowledge/actions";
import { useLocale, useT } from "@/i18n/client";
import { KNOWLEDGE_MAX_UPLOAD_BYTES, type KnowledgeDocumentOut, type KnowledgeListOut } from "@/lib/backend/agent-tools-types";

import { knowledgeErrorKey, knowledgeStatusTone, knowledgeUsageRatio } from "./lib";

type ActionResult<T> = { ok: true; data: T } | { ok: false; status: number; message: string; code?: string | null };

export type KnowledgeTableActions = {
  upload: (formData: FormData) => Promise<ActionResult<KnowledgeDocumentOut>>;
  addUrl: (body: { url: string; title?: string; ref?: string }) => Promise<ActionResult<KnowledgeDocumentOut>>;
  remove: (body: { id: string; ref?: string }) => Promise<ActionResult<null>>;
  reindex: (body: { id: string; ref?: string }) => Promise<ActionResult<KnowledgeDocumentOut>>;
  /** Spec 047 (12.2): deshacer «Eliminar» durante 10 minutos. Sin ella (la Guía del partner), eliminar no se deshace. */
  restore?: (body: { id: string; ref?: string }) => Promise<ActionResult<KnowledgeDocumentOut>>;
};

type Props = {
  refId: string;
  data: KnowledgeListOut;
  canWrite: boolean;
  actions?: KnowledgeTableActions;
  emptyCopy?: { title: string; body: string };
  /** Spec 047 (37.1): de qué capa son estas fuentes, cuando hay más de una. */
  layerNote?: string;
  /**
   * `playbook`: la Guía del partner como el prototipo «Consola de partners v2»
   * —«Subir archivo» con zona de soltar que sube al elegir, «Añadir URL» al lado
   * y la tarjeta «Documentos»—. El conocimiento del cliente usa `default`.
   */
  variant?: "default" | "playbook";
};

const ACCEPT = ".pdf,.txt,.md,.html,.htm,application/pdf,text/plain,text/markdown,text/html";

/**
 * Knowledge (CP-15): upload + URL forms, prompt-budget meter and the
 * document table (metadata only). Delete asks; reindex is one click.
 */
export function KnowledgeTable({ refId, data, canWrite, actions, emptyCopy, layerNote, variant = "default" }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [deleting, setDeleting] = React.useState<KnowledgeDocumentOut | null>(null);
  const [pending, startTransition] = React.useTransition();
  const ratio = knowledgeUsageRatio(data.indexed_chars, data.prompt_char_cap);
  const over = data.indexed_chars > data.prompt_char_cap && data.prompt_char_cap > 0;
  // Las fuentes de un cliente se recuperan durante 10 minutos; las de la Guía, no.
  const restore = actions ? actions.restore : (b: { id: string }) => restoreKnowledgeAction({ ref: refId, id: b.id });

  function reindex(doc: KnowledgeDocumentOut) {
    startTransition(async () => {
      const res = await (actions?.reindex ?? ((b) => reindexKnowledgeAction({ ref: refId, id: b.id })))(
        { ref: refId, id: doc.id },
      );
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("knowledge.reindexed", { title: doc.title }));
      router.refresh();
    });
  }
  async function confirmDelete() {
    if (!deleting) return;
    const doc = deleting;
    const res = await (actions?.remove ?? ((b) => deleteKnowledgeAction({ ref: refId, id: b.id })))(
      { ref: refId, id: doc.id },
    );
    if (!res.ok) return void toast.error(res.message);
    if (restore) {
      toast.success(t("knowledge.deleted.undo", { title: doc.title }), {
        action: { label: t("knowledge.undo"), onClick: () => undo(doc) },
      });
    } else toast.success(t("knowledge.deleted", { title: doc.title }));
    setDeleting(null);
    router.refresh();
  }
  function undo(doc: KnowledgeDocumentOut) {
    if (!restore) return;
    startTransition(async () => {
      const res = await restore({ ref: refId, id: doc.id });
      if (!res.ok) return void toast.error(res.code === "undo_window_closed" ? t("knowledge.undo.closed") : res.message);
      toast.success(t("knowledge.restored", { title: doc.title }));
      router.refresh();
    });
  }

  const forms = canWrite ? (
    <div className="grid gap-3 md:grid-cols-2">
      <UploadForm refId={refId} upload={actions?.upload} />
      <UrlForm refId={refId} addUrl={actions?.addUrl} />
    </div>
  ) : null;

  const docs = (
    data.items.length === 0 ? (
        <EmptyState icon={BookOpen} title={emptyCopy?.title ?? t("knowledge.empty.title")} description={emptyCopy?.body ?? t("knowledge.empty.body")} readonly />
      ) : (
        <div className="overflow-x-auto rounded-lg bg-card ring-1 ring-foreground/10">
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
                      {doc.status === "failed" ? <span className="max-w-64 text-xs text-pretty text-destructive">{t(knowledgeErrorKey(doc.error_code))}</span> : null}
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
      )
  );
  const usageText = t("knowledge.usage", { used: formatNumber(data.indexed_chars, locale), cap: formatNumber(data.prompt_char_cap, locale) });
  const confirm = (
    <ConfirmDialog
      open={deleting !== null}
      onOpenChange={(o) => !o && setDeleting(null)}
      title={t("knowledge.delete.title", { title: deleting?.title ?? "" })}
      description={variant === "playbook" ? t("proto.guide.delete.body") : t(restore ? "knowledge.delete.body.undo" : "knowledge.delete.body")}
      confirmLabel={t("knowledge.delete")}
      cancelLabel={t("common.cancel")}
      destructive
      onConfirm={confirmDelete}
    />
  );

  if (variant === "playbook") {
    return (
      <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
        {!canWrite ? <p className="text-xs text-muted-foreground">{t("knowledge.readonly")}</p> : null}
        {canWrite ? (
          <div className="grid min-w-0 items-start gap-4 lg:grid-cols-2">
            <PlaybookUpload upload={actions?.upload} />
            <UrlForm refId={refId} addUrl={actions?.addUrl} variant="playbook" />
          </div>
        ) : null}
        <section aria-labelledby="kn-docs-h" className="grid min-w-0 gap-4 rounded-lg bg-card p-4 ring-1 ring-foreground/10" data-slot="knowledge-docs">
          <div className="flex min-w-0 items-center justify-between gap-3">
            <h2 id="kn-docs-h" className="text-base font-semibold">
              {t("proto.guide.docs")}
            </h2>
            <span className="text-xs text-muted-foreground tabular-nums">{formatNumber(data.items.length, locale)}</span>
          </div>
          <Meter
            label={t("knowledge.usage.label")}
            value={data.indexed_chars}
            max={data.prompt_char_cap > 0 ? data.prompt_char_cap : null}
            // Prototipo: ámbar desde el 90 %, rojo al pasarse.
            tone={over ? "danger" : ratio >= 0.9 ? "warning" : "positive"}
            valueLabel={t("proto.guide.usage", {
              used: formatNumber(data.indexed_chars, locale),
              cap: formatNumber(data.prompt_char_cap, locale),
              pct: formatNumber(ratio, locale, { style: "percent", maximumFractionDigits: 0 }),
            })}
            noMaxLabel={usageText}
            hint={over ? <span className="text-destructive">{t("knowledge.usage.over")}</span> : undefined}
          />
          {docs}
        </section>
        {confirm}
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
      {layerNote ? <p className="max-w-prose text-sm text-pretty text-muted-foreground" data-slot="knowledge-layer">{layerNote}</p> : null}
      {!canWrite ? <p className="text-xs text-muted-foreground">{t("knowledge.readonly")}</p> : null}
      {forms}

      <Meter
        label={t("knowledge.usage.label")}
        value={data.indexed_chars}
        max={data.prompt_char_cap > 0 ? data.prompt_char_cap : null}
        tone={over ? "danger" : "auto"}
        valueLabel={`${t("knowledge.usage", { used: formatNumber(data.indexed_chars, locale), cap: formatNumber(data.prompt_char_cap, locale) })} · ${formatNumber(ratio, locale, { style: "percent", maximumFractionDigits: 0 })}`}
        noMaxLabel={t("knowledge.usage", { used: formatNumber(data.indexed_chars, locale), cap: formatNumber(data.prompt_char_cap, locale) })}
        hint={over ? <span className="text-destructive">{t("knowledge.usage.over")}</span> : undefined}
      />

      {docs}

      {confirm}
    </div>
  );
}

function UploadForm({ refId, upload }: { refId: string; upload?: KnowledgeTableActions["upload"] }) {
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
      const res = await (upload ?? uploadKnowledgeAction)(fd);
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

function UrlForm({ refId, addUrl, variant = "default" }: { refId: string; addUrl?: KnowledgeTableActions["addUrl"]; variant?: "default" | "playbook" }) {
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
      const res = await (addUrl ?? addKnowledgeUrlAction)({ ref: refId, url: url.trim(), title: title.trim() || undefined });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("knowledge.url.done", { title: res.data.title }));
      setUrl("");
      setTitle("");
      router.refresh();
    });
  }

  if (variant === "playbook") {
    // Prototipo: «URL pública» (https://…), «Título · opcional» y «Añadir e indexar».
    return (
      <section aria-labelledby="kn-url-h" className="grid min-w-0 gap-4 rounded-lg bg-card p-4 ring-1 ring-foreground/10" data-slot="knowledge-url">
        <h2 id="kn-url-h" className="text-base font-semibold">
          {t("knowledge.url.title")}
        </h2>
        <form onSubmit={submit} className="grid gap-4" aria-busy={pending} noValidate>
          <div className="grid gap-2">
            <Label htmlFor="kn-url">{t("proto.guide.url")}</Label>
            <Input id="kn-url" type="url" inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} maxLength={2048} placeholder="https://…" spellCheck={false} autoComplete="off" aria-invalid={error ? true : undefined} aria-describedby={error ? "kn-url-err" : undefined} />
            {error ? (
              <p id="kn-url-err" className="text-xs text-destructive" aria-live="polite">
                {error}
              </p>
            ) : null}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="kn-url-title">
              {t("proto.guide.title")} <span className="font-normal text-muted-foreground">· {t("proto.guide.optional")}</span>
            </Label>
            <Input id="kn-url-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} autoComplete="off" />
          </div>
          <div>
            <Button type="submit" disabled={pending}>
              {t("knowledge.url.submit")}
            </Button>
          </div>
        </form>
      </section>
    );
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

/**
 * «Subir archivo» de la Guía del partner (prototipo): una zona de soltar con
 * «Elegir archivo», que sube en cuanto se elige o se suelta el archivo —sin
 * otro botón—, y el título opcional debajo. El campo de archivo es real y
 * accesible: está oculto a la vista pero se enfoca, y «Elegir archivo» es su
 * etiqueta, que pinta el foco del campo.
 */
function PlaybookUpload({ upload }: { upload?: KnowledgeTableActions["upload"] }) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [title, setTitle] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [sending, setSending] = React.useState<string | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  function send(file: File) {
    if (file.size === 0) return void setError(t("knowledge.upload.noFile"));
    if (file.size > KNOWLEDGE_MAX_UPLOAD_BYTES) return void setError(t("knowledge.upload.tooLarge"));
    setError(null);
    const fd = new FormData();
    fd.set("file", file);
    fd.set("ref", "");
    if (title.trim()) fd.set("title", title.trim());
    setSending(file.name);
    startTransition(async () => {
      const res = await (upload ?? uploadKnowledgeAction)(fd);
      setSending(null);
      if (inputRef.current) inputRef.current.value = "";
      if (!res.ok) return void toast.error(res.status === 413 ? t("knowledge.upload.tooLarge") : res.message);
      toast.success(t("knowledge.upload.done", { title: res.data.title }));
      setTitle("");
      router.refresh();
    });
  }

  return (
    <section aria-labelledby="kn-upload-h" className="grid min-w-0 gap-4 rounded-lg bg-card p-4 ring-1 ring-foreground/10" data-slot="knowledge-upload" aria-busy={pending}>
      <h2 id="kn-upload-h" className="text-base font-semibold">
        {t("knowledge.upload.title")}
      </h2>
      <div
        data-slot="knowledge-drop"
        data-dragging={dragging || undefined}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer?.files?.[0];
          if (file && !pending) send(file);
        }}
        className={cn(
          "flex min-w-0 flex-wrap items-center justify-center gap-3 rounded-lg border border-dashed border-input px-4 py-4 text-center text-sm text-muted-foreground transition-colors",
          dragging && "border-primary bg-status-positive-bg",
        )}
      >
        <Upload aria-hidden="true" className="size-4 shrink-0" />
        <span>{t("proto.guide.drop")}</span>
        <input
          ref={inputRef}
          id="kn-file"
          type="file"
          accept={ACCEPT}
          className="peer sr-only"
          disabled={pending}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "kn-file-err" : undefined}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) send(file);
          }}
        />
        <label
          htmlFor="kn-file"
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            "cursor-pointer peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-ring peer-disabled:pointer-events-none peer-disabled:opacity-50",
          )}
        >
          {t("proto.guide.choose")}
        </label>
      </div>
      {sending ? (
        <p className="text-sm text-muted-foreground" role="status">
          {t("proto.guide.uploading", { name: sending })}
        </p>
      ) : null}
      {error ? (
        <p id="kn-file-err" className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div className="grid gap-2">
        <Label htmlFor="kn-title">
          {t("proto.guide.title")} <span className="font-normal text-muted-foreground">· {t("proto.guide.optional")}</span>
        </Label>
        <Input id="kn-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} autoComplete="off" />
      </div>
    </section>
  );
}
