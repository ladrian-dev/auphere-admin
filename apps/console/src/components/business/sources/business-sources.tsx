"use client";

import { FileText, Globe, RefreshCw, Trash2, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input, Skeleton, StatusBadge, formatBytes, formatRelative } from "@nexus/ui";

import {
  addSourceUrlAction,
  listSourcesAction,
  removeSourceAction,
  rereadSourceAction,
  restoreSourceAction,
  uploadSourceAction,
} from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Source, Sources } from "@/lib/backend/client-records";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type Result<T> = { ok: true; data: T } | Failed;
type Accepted = { source: Source; job_id: string };

export type BusinessSourcesActions = {
  load: (body: { ref: string }) => Promise<Result<Sources>>;
  upload: (form: FormData) => Promise<Result<Accepted>>;
  addUrl: (body: { ref: string; url: string }) => Promise<Result<Accepted>>;
  reread: (body: { ref: string; id: string }) => Promise<Result<Accepted>>;
  remove: (body: { ref: string; id: string }) => Promise<Result<{ id: string; restore_until: string }>>;
  restore: (body: { ref: string; id: string }) => Promise<Result<Source>>;
};

const DEFAULT_ACTIONS: BusinessSourcesActions = {
  load: (b) => listSourcesAction(b),
  upload: (f) => uploadSourceAction(f),
  addUrl: (b) => addSourceUrlAction(b),
  reread: (b) => rereadSourceAction(b),
  remove: (b) => removeSourceAction(b),
  restore: (b) => restoreSourceAction(b),
};

/** Lo que se espera entre consultas mientras algo se lee (1, 2, 4… hasta 10 s). */
export function nextDelay(round: number): number {
  return Math.min(10_000, 1_000 * 2 ** Math.max(0, round));
}

function timeOf(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

const KNOWN = new Set(["too_large", "unsupported_type", "invalid_url", "undo_window_closed"]);

/**
 * «Documentos y webs» de la ficha (spec 047, T071, requisito 12): subir un
 * archivo de hasta 10 MB o añadir una web; cada fuente dice si se está leyendo,
 * si se leyó y cuándo, o por qué no se pudo; «Volver a leer» y «Quitar», que
 * deja de usarse desde el siguiente mensaje y se puede recuperar durante 10
 * minutos. Leer es un trabajo en segundo plano: mientras algo se lee, la lista
 * se vuelve a consultar con espera creciente.
 */
export function BusinessSources({
  refId,
  initial,
  canWrite,
  actions,
  bare = false,
}: {
  refId: string;
  initial?: Sources | null;
  canWrite: boolean;
  actions?: Partial<BusinessSourcesActions>;
  /** Dentro de la tarjeta de Negocio, que ya pone el título. */
  bare?: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const act = React.useMemo(() => ({ ...DEFAULT_ACTIONS, ...actions }), [actions]);
  const [data, setData] = React.useState<Sources | null | undefined>(initial);
  const [failed, setFailed] = React.useState(false);
  const [url, setUrl] = React.useState("");
  const [busy, startTransition] = React.useTransition();
  const [round, setRound] = React.useState(0);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const ids = { url: React.useId(), file: React.useId() };

  const load = React.useCallback(async () => {
    const res = await act.load({ ref: refId });
    if (res.ok) {
      setData(res.data);
      setFailed(false);
    } else {
      setFailed(true);
    }
  }, [act, refId]);

  React.useEffect(() => {
    if (initial !== undefined) return;
    // Fuera del cuerpo del efecto: cargar pone estado.
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [initial, load]);

  const reading = Boolean(data?.items.some((s) => s.status === "reading"));
  React.useEffect(() => {
    if (!reading) return;
    const handle = window.setTimeout(() => {
      void load().then(() => setRound((r) => r + 1));
    }, nextDelay(round));
    return () => window.clearTimeout(handle);
  }, [reading, round, load]);

  function fail(res: Failed) {
    toast.error(res.code && KNOWN.has(res.code) ? t(`business.sources.error.${res.code}` as MessageKey) : t("business.sources.error.generic"));
  }

  function accepted(res: Result<Accepted>) {
    if (!res.ok) return fail(res);
    setRound(0);
    void load();
  }

  function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (data && file.size > data.max_bytes) {
      toast.error(t("business.sources.error.too_large"));
      return;
    }
    const form = new FormData();
    form.set("ref", refId);
    form.set("file", file, file.name);
    startTransition(async () => accepted(await act.upload(form)));
  }

  function addUrl(event: React.FormEvent) {
    event.preventDefault();
    const value = url.trim();
    if (!/^https?:\/\//i.test(value)) {
      toast.error(t("business.sources.error.invalid_url"));
      return;
    }
    startTransition(async () => {
      const res = await act.addUrl({ ref: refId, url: value });
      if (res.ok) setUrl("");
      accepted(res);
    });
  }

  function remove(source: Source) {
    startTransition(async () => {
      const res = await act.remove({ ref: refId, id: source.id });
      if (!res.ok) return fail(res);
      void load();
      toast.success(t("business.sources.removed"), {
        action: { label: t("clients.v2.undo"), onClick: () => restore(source.id) },
      });
    });
  }

  function restore(id: string) {
    startTransition(async () => {
      const res = await act.restore({ ref: refId, id });
      if (!res.ok) return fail(res);
      toast.success(t("business.sources.restored"));
      void load();
    });
  }

  function status(s: Source) {
    if (s.status === "reading") return <StatusBadge tone="info" pulse>{t("business.sources.status.reading")}</StatusBadge>;
    if (s.status === "failed") {
      const reason = s.failure ? t(`business.sources.failure.${s.failure}` as MessageKey) : t("business.sources.failure.unreachable");
      return <StatusBadge tone="danger">{t("business.sources.status.failed", { reason })}</StatusBadge>;
    }
    return <StatusBadge tone="positive">{t("business.sources.status.read", { when: formatRelative(s.read_at, locale) })}</StatusBadge>;
  }

  const Wrap = bare ? "div" : "section";
  return (
    <Wrap className="grid min-w-0 gap-4" aria-labelledby={bare ? undefined : `${ids.file}-title`} data-slot="business-sources">
      <div className="grid min-w-0 gap-1">
        {bare ? null : (
          <h2 id={`${ids.file}-title`} className="text-base font-semibold text-balance">
            {t("business.sources.title")}
          </h2>
        )}
        <p className="text-sm text-muted-foreground text-pretty">{t("business.sources.intro")}</p>
      </div>

      {canWrite ? (
        <div className="grid min-w-0 gap-3 sm:grid-cols-[auto_1fr] sm:items-end">
          <div className="grid gap-1">
            <input
              ref={fileRef}
              id={ids.file}
              type="file"
              className="sr-only"
              accept=".pdf,.doc,.docx,.txt,.md,.html,.htm,.jpg,.jpeg,.png,.webp,application/pdf,text/plain,text/markdown,text/html,image/*"
              onChange={onFile}
              aria-label={t("business.sources.upload")}
            />
            <Button type="button" variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}>
              <Upload aria-hidden="true" />
              {busy ? t("business.sources.uploading") : t("business.sources.upload")}
            </Button>
          </div>
          <form onSubmit={addUrl} className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-end">
            <Field label={t("business.sources.url")} htmlFor={ids.url} className="min-w-0 flex-1">
              {(a11y) => (
                <Input {...a11y} type="url" inputMode="url" value={url} maxLength={2048} placeholder={t("business.sources.url.placeholder")} onChange={(e) => setUrl(e.target.value)} />
              )}
            </Field>
            <Button type="submit" variant="outline" disabled={busy || !url.trim()}>
              <Globe aria-hidden="true" />
              {t("business.sources.addUrl")}
            </Button>
          </form>
          <p className="text-xs text-muted-foreground sm:col-span-2">{t("business.sources.limit")}</p>
        </div>
      ) : null}

      {failed && !data ? (
        <div role="alert" className="grid gap-2">
          <p className="text-sm">{t("business.sources.error")}</p>
          <Button type="button" size="sm" variant="outline" className="justify-self-start" onClick={() => void load()}>
            {t("panel.retry")}
          </Button>
        </div>
      ) : data === undefined || data === null ? (
        <div role="status" className="grid gap-2" aria-busy="true" aria-label={t("business.sources.loading")}>
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("business.sources.empty")}</p>
      ) : (
        <ul className="grid min-w-0 gap-2" aria-label={t("business.sources.list")}>
          {data.items.map((s) => (
            <li key={s.id} className="flex min-w-0 flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-start gap-2">
                {s.kind === "web" ? <Globe aria-hidden="true" className="mt-1 size-4 shrink-0" /> : <FileText aria-hidden="true" className="mt-1 size-4 shrink-0" />}
                <div className="grid min-w-0 gap-1">
                  <span className="truncate text-sm font-medium" title={s.title}>
                    {s.title}
                  </span>
                  <span className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {status(s)}
                    {s.kind === "file" ? <span className="tabular-nums">{formatBytes(s.size_bytes, locale)}</span> : null}
                  </span>
                </div>
              </div>
              {canWrite && data.allowed.length ? (
                <div className="flex shrink-0 gap-2">
                  <Button type="button" size="sm" variant="ghost" disabled={busy || s.status === "reading"} onClick={() => startTransition(async () => accepted(await act.reread({ ref: refId, id: s.id })))}>
                    <RefreshCw aria-hidden="true" />
                    {t("business.sources.reread")}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => remove(s)} aria-label={t("business.sources.remove", { title: s.title })}>
                    <Trash2 aria-hidden="true" />
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {data && data.removed.length > 0 && canWrite ? (
        <div className="grid min-w-0 gap-2">
          <p className="text-xs font-medium text-muted-foreground">{t("business.sources.removedList")}</p>
          <ul className="grid min-w-0 gap-2">
            {data.removed.map((r) => (
              <li key={r.id} className="flex min-w-0 flex-wrap items-center justify-between gap-2 text-sm">
                <span className="min-w-0 truncate" title={r.title}>
                  {r.title}
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">{t("business.sources.restoreUntil", { time: timeOf(r.restore_until, locale) })}</span>
                  <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => restore(r.id)} aria-label={t("business.sources.restore", { title: r.title })}>
                    {t("clients.v2.undo")}
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Wrap>
  );
}
