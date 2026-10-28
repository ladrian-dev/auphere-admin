"use client";

import { BookOpen, FileUp, GraduationCap, Link2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Field, Input, StatusBadge, formatBytes, formatDateTime } from "@nexus/ui";

import {
  addAgentKnowledgeUrlAction,
  agentKnowledgeAction,
  forgetTaughtAction,
  removeAgentKnowledgeAction,
  restoreAgentKnowledgeAction,
  teachAction,
  uploadAgentKnowledgeAction,
} from "@/app/(console)/clients/[ref]/agents/knowledge-actions";
import { knowledgeErrorKey, knowledgeStatusTone } from "@/components/agent-tools/lib";
import { RowActions } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AgentKnowledge, KnowledgeSource, TeachScope } from "@/lib/backend/agent-knowledge-types";
import { KNOWLEDGE_MAX_UPLOAD_BYTES } from "@/lib/backend/agent-tools-types";

import type { Result } from "./builder-model";
import { businessKnowledgeHref, businessLineKey, formatClock, isWebAddress, sourceKindKey, visibleSources } from "./knowledge-model";
import { TeachDialog } from "./teach-dialog";

type Ids = { ref: string; agent: string };
export type AgentKnowledgeActions = {
  reload: (body: Ids) => Promise<Result<AgentKnowledge>>;
  upload: (form: FormData) => Promise<Result<KnowledgeSource>>;
  addUrl: (body: Ids & { url: string; title?: string }) => Promise<Result<KnowledgeSource>>;
  remove: (body: Ids & { doc: string }) => Promise<Result<null>>;
  restore: (body: Ids & { doc: string }) => Promise<Result<KnowledgeSource>>;
  teach: (body: Ids & { text: string; scope: TeachScope }) => Promise<Result<KnowledgeSource>>;
  forget: (body: Ids & { doc: string; scope: TeachScope }) => Promise<Result<null>>;
};

export const KNOWLEDGE_ACTIONS: AgentKnowledgeActions = {
  reload: (body) => agentKnowledgeAction(body),
  upload: (form) => uploadAgentKnowledgeAction(form),
  addUrl: (body) => addAgentKnowledgeUrlAction(body),
  remove: (body) => removeAgentKnowledgeAction(body),
  restore: (body) => restoreAgentKnowledgeAction(body),
  teach: (body) => teachAction(body),
  forget: (body) => forgetTaughtAction(body),
};

const ACCEPT = ".pdf,.txt,.md,.html,.htm,application/pdf,text/plain,text/markdown,text/html";

/**
 * La sección Conocimiento de un agente (spec 047, historia 22; T134, requisitos
 * 37.3 y 12.1): las fuentes propias de este agente —que no ve ningún otro, la
 * garantía 9— con su estado, su tamaño y cuándo se leyeron, y cuántas fuentes
 * del negocio sabe además, con el camino a Negocio, donde se gestionan.
 *
 * Quien puede escribir sube un archivo o añade una web solo para él, quita una
 * fuente (deja de usarse desde el siguiente mensaje y se puede deshacer durante
 * 10 minutos: la fila se queda con «Deshacer» mientras tanto) y «Enseña» algo
 * eligiendo siempre el alcance. Quien solo lee lo ve todo sin botones (§V).
 */
export function AgentKnowledgePanel({
  refId,
  agentId,
  agentName,
  knowledge: initial,
  canWrite,
  onTaught,
  actions = KNOWLEDGE_ACTIONS,
}: {
  refId: string;
  agentId: string;
  agentName: string;
  /** `null` si no se pudo leer: se dice y se deja reintentar. */
  knowledge: AgentKnowledge | null;
  canWrite: boolean;
  /** Se enseñó algo: las pruebas de los agentes que lo saben se vuelven a pasar. */
  onTaught?: () => void;
  actions?: AgentKnowledgeActions;
}) {
  const t = useT();
  const locale = useLocale();
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [data, setData] = React.useState(initial);
  const [adding, setAdding] = React.useState<"file" | "url" | null>(null);
  const [teaching, setTeaching] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [notice, setNotice] = React.useState<KnowledgeSource | null>(null);

  const reload = React.useCallback(async () => {
    const res = await actions.reload(ids);
    if (res.ok) setData(res.data);
    return res.ok;
  }, [actions, ids]);

  const fail = () => toast.error(t("builder.knowledge.error.generic"));

  async function restore(doc: KnowledgeSource) {
    setBusy(true);
    const res = await actions.restore({ ...ids, doc: doc.id });
    setBusy(false);
    if (!res.ok) {
      toast.error(res.code === "undo_window_closed" ? t("builder.knowledge.undo.closed") : t("builder.knowledge.error.generic"));
      await reload();
      return;
    }
    toast.success(t("builder.knowledge.restored", { title: doc.title }));
    await reload();
  }

  async function remove(doc: KnowledgeSource) {
    setBusy(true);
    const res = await actions.remove({ ...ids, doc: doc.id });
    setBusy(false);
    if (!res.ok) return fail();
    toast.success(t("builder.knowledge.removed", { title: doc.title }), {
      action: { label: t("builder.knowledge.undo"), onClick: () => void restore(doc) },
    });
    await reload();
  }

  async function forget(doc: KnowledgeSource, scope: TeachScope) {
    const res = await actions.forget({ ...ids, doc: doc.id, scope });
    if (!res.ok) return fail();
    setNotice(null);
    toast.success(t("builder.teach.undone"));
    await reload();
  }

  async function teach(body: { text: string; scope: TeachScope }): Promise<string | null> {
    const res = await actions.teach({ ...ids, ...body });
    if (!res.ok) {
      if (res.code === "teach_too_long") return t("builder.teach.tooLong");
      if (res.code === "teach_empty") return t("builder.teach.required.text");
      return res.status === 401 || res.status === 403 ? t("common.forbidden") : t("builder.knowledge.error.generic");
    }
    const doc = res.data;
    setTeaching(false);
    toast.success(body.scope === "agent" ? t("builder.teach.done.agent", { name: agentName }) : t("builder.teach.done.business"), {
      action: { label: t("builder.teach.undo"), onClick: () => void forget(doc, body.scope) },
    });
    // Lo enseñado al negocio no sale en esta lista: se dice aquí, con su deshacer.
    setNotice(body.scope === "business" ? doc : null);
    await reload();
    onTaught?.();
    return null;
  }

  if (!data) {
    return (
      <Callout
        tone="danger"
        action={
          <Button size="sm" variant="outline" onClick={() => void reload()}>
            {t("builder.knowledge.retry")}
          </Button>
        }
      >
        {t("builder.knowledge.error.load")}
      </Callout>
    );
  }

  const { live, restorable } = visibleSources(data.items);
  const liveMenu = foldsIntoMenu(canWrite ? live.length : 0);
  const restoreMenu = foldsIntoMenu(canWrite ? restorable.length : 0);

  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-knowledge" aria-busy={busy}>
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("builder.knowledge.intro")}</p>
      <p className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1 text-sm" data-slot="business-sources">
        <span className="text-pretty">{t(businessLineKey(data.business_sources), { n: data.business_sources })}</span>
        <Link href={businessKnowledgeHref(refId)} className="font-medium text-primary-text underline-offset-4 hover:underline">
          {t("builder.knowledge.business.link")}
        </Link>
      </p>

      {canWrite ? (
        <div className="flex min-w-0 flex-wrap gap-2" data-slot="knowledge-tools">
          <Button size="sm" onClick={() => setTeaching(true)}>
            <GraduationCap aria-hidden="true" />
            {t("builder.teach.open")}
          </Button>
          <Button size="sm" variant="outline" aria-expanded={adding === "file"} onClick={() => setAdding(adding === "file" ? null : "file")}>
            <FileUp aria-hidden="true" />
            {t("builder.knowledge.add.file")}
          </Button>
          <Button size="sm" variant="outline" aria-expanded={adding === "url"} onClick={() => setAdding(adding === "url" ? null : "url")}>
            <Link2 aria-hidden="true" />
            {t("builder.knowledge.add.url")}
          </Button>
        </div>
      ) : null}

      {canWrite && adding === "file" ? (
        <FileForm
          ids={ids}
          upload={actions.upload}
          onCancel={() => setAdding(null)}
          onAdded={async (doc) => {
            setAdding(null);
            toast.success(doc.status === "failed" ? t("builder.knowledge.addedFailed", { title: doc.title }) : t("builder.knowledge.added", { title: doc.title }));
            await reload();
          }}
        />
      ) : null}
      {canWrite && adding === "url" ? (
        <UrlForm
          ids={ids}
          addUrl={actions.addUrl}
          onCancel={() => setAdding(null)}
          onAdded={async (doc) => {
            setAdding(null);
            toast.success(doc.status === "failed" ? t("builder.knowledge.addedFailed", { title: doc.title }) : t("builder.knowledge.added", { title: doc.title }));
            await reload();
          }}
        />
      ) : null}

      {notice ? (
        <Callout
          tone="positive"
          action={
            <span className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => void forget(notice, "business")}>
                {t("builder.teach.undo")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setNotice(null)}>
                {t("builder.teach.dismiss")}
              </Button>
            </span>
          }
        >
          {t("builder.teach.business.notice", { title: notice.title })}
        </Callout>
      ) : null}

      {live.length === 0 && restorable.length === 0 ? (
        <div className="grid min-w-0 justify-items-start gap-1 rounded-md border border-dashed border-border p-4 text-sm" data-slot="knowledge-empty">
          <BookOpen aria-hidden="true" className="size-5 text-muted-foreground" />
          <p className="font-medium text-balance">{t("builder.knowledge.empty.title")}</p>
          <p className="text-pretty text-muted-foreground">{canWrite ? t("builder.knowledge.empty.body") : t("builder.knowledge.empty.readonly")}</p>
        </div>
      ) : null}

      {live.length ? (
        <ul aria-label={t("builder.knowledge.list")} className="grid min-w-0 divide-y divide-border rounded-md border border-border">
          {live.map((doc) => (
            <SourceRow key={doc.id} doc={doc} locale={locale}>
              {canWrite ? (
                <RowButton
                  menu={liveMenu}
                  label={t("builder.knowledge.remove")}
                  fullLabel={t("builder.knowledge.remove.label", { title: doc.title })}
                  menuLabel={t("builder.knowledge.actions", { title: doc.title })}
                  disabled={busy}
                  onSelect={() => void remove(doc)}
                />
              ) : null}
            </SourceRow>
          ))}
        </ul>
      ) : null}

      {restorable.length ? (
        <ul aria-label={t("builder.knowledge.restorable")} className="grid min-w-0 gap-2" data-slot="knowledge-restorable">
          {restorable.map((doc) => (
            <li key={doc.id} className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-md border border-dashed border-border px-3 py-2 text-sm">
              <span className="grid min-w-0 gap-1">
                <span className="min-w-0 break-words text-muted-foreground line-through">{doc.title}</span>
                <span className="text-xs text-muted-foreground">
                  {t("builder.knowledge.removed.row", { time: formatClock(doc.restore_until, locale) })}
                </span>
              </span>
              {canWrite ? (
                <RowButton
                  menu={restoreMenu}
                  label={t("builder.knowledge.undo")}
                  fullLabel={t("builder.knowledge.undo.label", { title: doc.title })}
                  menuLabel={t("builder.knowledge.actions", { title: doc.title })}
                  disabled={busy}
                  onSelect={() => void restore(doc)}
                />
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {teaching ? <TeachDialog agentName={agentName} onOpenChange={setTeaching} onTeach={teach} /> : null}
    </div>
  );
}

/** Una acción por fila: botón mientras la lista tiene pocas, ⋯ cuando pasa de dos (regla del owner). */
function RowButton({
  menu,
  label,
  fullLabel,
  menuLabel,
  disabled,
  onSelect,
}: {
  menu: boolean;
  label: string;
  fullLabel: string;
  menuLabel: string;
  disabled?: boolean;
  onSelect: () => void;
}) {
  if (menu) return <RowActions menu actions={[{ label, onSelect, primary: true }]} ariaLabel={menuLabel} />;
  return (
    <Button size="sm" variant="outline" onClick={onSelect} disabled={disabled} aria-label={fullLabel}>
      {label}
    </Button>
  );
}

function SourceRow({ doc, locale, children }: { doc: KnowledgeSource; locale: "es" | "en"; children?: React.ReactNode }) {
  const t = useT();
  return (
    <li className="flex min-w-0 flex-wrap items-start justify-between gap-3 p-3" data-slot="knowledge-source">
      <div className="grid min-w-0 flex-1 basis-56 gap-1">
        {doc.kind === "url" && doc.source_url ? (
          <a href={doc.source_url} target="_blank" rel="noopener noreferrer" className="min-w-0 font-medium break-words underline-offset-4 hover:underline">
            {doc.title}
          </a>
        ) : (
          <span className="min-w-0 font-medium break-words">{doc.title}</span>
        )}
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{t(sourceKindKey(doc.kind))}</span>
          <StatusBadge tone={knowledgeStatusTone(doc.status)} pulse={doc.status === "pending"}>
            {t(`knowledge.status.${doc.status}` as MessageKey)}
          </StatusBadge>
          {doc.size_bytes > 0 ? <span className="tabular-nums">{formatBytes(doc.size_bytes, locale)}</span> : null}
          <span className="tabular-nums">
            {doc.indexed_at ? t("builder.knowledge.read", { date: formatDateTime(doc.indexed_at, locale) }) : t("builder.knowledge.notRead")}
          </span>
        </span>
        {doc.status === "failed" ? <span className="text-xs text-pretty text-destructive">{t(knowledgeErrorKey(doc.error_code))}</span> : null}
      </div>
      {children ? <div className="shrink-0">{children}</div> : null}
    </li>
  );
}

function FileForm({
  ids,
  upload,
  onCancel,
  onAdded,
}: {
  ids: Ids;
  upload: AgentKnowledgeActions["upload"];
  onCancel: () => void;
  onAdded: (doc: KnowledgeSource) => void | Promise<void>;
}) {
  const t = useT();
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const input = React.useRef<HTMLInputElement>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // El archivo se lee del campo, no de `new FormData(form)`: así no depende de cómo lo arme el navegador.
    const file = input.current?.files?.[0];
    if (!file || file.size === 0) return setError(t("builder.knowledge.file.required"));
    if (file.size > KNOWLEDGE_MAX_UPLOAD_BYTES) return setError(t("builder.knowledge.file.tooLarge"));
    setError(null);
    const form = new FormData();
    form.set("ref", ids.ref);
    form.set("agent", ids.agent);
    form.set("file", file, file.name);
    if (title.trim()) form.set("title", title.trim());
    setBusy(true);
    const res = await upload(form);
    setBusy(false);
    if (!res.ok) return setError(res.status === 413 ? t("builder.knowledge.file.tooLarge") : t("builder.knowledge.error.generic"));
    await onAdded(res.data);
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-3 rounded-md border border-border p-3" data-slot="knowledge-file-form">
      <Field label={t("builder.knowledge.file.field")} error={error ?? undefined} required>
        {(a11y) => <Input {...a11y} ref={input} name="file" type="file" accept={ACCEPT} />}
      </Field>
      <Field label={t("builder.knowledge.title.field")}>
        {(a11y) => <Input {...a11y} name="title" value={title} maxLength={255} autoComplete="off" onChange={(e) => setTitle(e.target.value)} />}
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" loading={busy}>
          {t("builder.knowledge.file.submit")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("builder.knowledge.cancel")}
        </Button>
      </div>
    </form>
  );
}

function UrlForm({
  ids,
  addUrl,
  onCancel,
  onAdded,
}: {
  ids: Ids;
  addUrl: AgentKnowledgeActions["addUrl"];
  onCancel: () => void;
  onAdded: (doc: KnowledgeSource) => void | Promise<void>;
}) {
  const t = useT();
  const [url, setUrl] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!isWebAddress(url)) return setError(t("builder.knowledge.url.invalid"));
    setError(null);
    setBusy(true);
    const res = await addUrl({ ...ids, url: url.trim(), ...(title.trim() ? { title: title.trim() } : {}) });
    setBusy(false);
    if (!res.ok) return setError(t("builder.knowledge.error.generic"));
    await onAdded(res.data);
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-3 rounded-md border border-border p-3" data-slot="knowledge-url-form">
      <Field label={t("builder.knowledge.url.field")} error={error ?? undefined} required>
        {(a11y) => (
          <Input
            {...a11y}
            type="url"
            inputMode="url"
            value={url}
            maxLength={2048}
            placeholder="https://"
            spellCheck={false}
            autoComplete="off"
            onChange={(e) => setUrl(e.target.value)}
          />
        )}
      </Field>
      <Field label={t("builder.knowledge.title.field")}>
        {(a11y) => <Input {...a11y} value={title} maxLength={255} autoComplete="off" onChange={(e) => setTitle(e.target.value)} />}
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" loading={busy}>
          {t("builder.knowledge.url.submit")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("builder.knowledge.cancel")}
        </Button>
      </div>
    </form>
  );
}
