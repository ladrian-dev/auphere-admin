"use client";

import { CircleCheck, ExternalLink, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  SegmentedControl,
  Skeleton,
  StatusBadge,
  buttonVariants,
  formatDateTime,
} from "@nexus/ui";

import {
  agentConnectorsAction,
  connectConnectorAction,
  reconnectConnectionAction,
  removeActivationAction,
  setActivationAction,
} from "@/app/(console)/clients/[ref]/agents/connector-actions";
import { connectApiKeyAction } from "@/app/(console)/clients/[ref]/integrations/actions";
import { connectorStatusKey, splitCredentials } from "@/components/agent-tools/lib";
import { useLocale, useT } from "@/i18n/client";
import type {
  Activation,
  AffectedSkills,
  AgentConnector,
  ConnectConsent,
  ConnectFormField,
  ConnectResult,
  ConnectorPermission,
  ConnectorSettings,
} from "@/lib/backend/agent-connectors-types";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";
import type { AgentSpec } from "@/lib/backend/builder-types";

import { skillName, type Result } from "./builder-model";
import { ConnectorLogo, CredentialsForm, PermissionRadios, SettingsDialog } from "./connector-parts";
import {
  CONNECTED_FILTER,
  authKindLabel,
  categoriesOf,
  categoryLabel,
  categoryOf,
  connectionHref,
  descriptionKey,
  filterConnectors,
  filterCounts,
  isBroken,
  orderConnectors,
  permissionLabel,
  rowActions,
  rowState,
  skillsUsing,
} from "./connector-model";

type Ids = { ref: string; agent: string };
export type AgentConnectorsActions = {
  load?: (body: Ids) => Promise<Result<AgentConnector[]>>;
  connect?: (body: Ids & { slug: string; permission: ConnectorPermission }) => Promise<Result<ConnectResult>>;
  activate?: (body: Ids & { slug: string; permission: ConnectorPermission; settings: ConnectorSettings }) => Promise<Result<Activation>>;
  remove?: (body: Ids & { slug: string }) => Promise<Result<AffectedSkills>>;
  reconnect?: (body: { ref: string; connection: string }) => Promise<Result<ConnectConsent>>;
  saveKey?: (body: { ref: string; slug: string; secrets: Record<string, string>; endpoint_meta: Record<string, unknown> }) => Promise<Result<ConnectorOut>>;
  /** Abrir la autorización del proveedor (los tests no abren ventanas). */
  open?: (url: string) => void;
};

const SERVER_ACTIONS: Required<AgentConnectorsActions> = {
  load: (body) => agentConnectorsAction(body),
  connect: (body) => connectConnectorAction(body),
  activate: (body) => setActivationAction(body),
  remove: (body) => removeActivationAction(body),
  reconnect: (body) => reconnectConnectionAction(body),
  saveKey: (body) => connectApiKeyAction(body),
  open: (url) => void window.open(url, "_blank", "noopener,noreferrer"),
};

const NO_ACTIONS: AgentConnectorsActions = {};
/** «Todos» en el filtro segmentado. */
const ALL = "all";

/** Una autorización abierta en otra ventana: el enlace por si el navegador la bloqueó. */
type Pending = { slug: string; name: string; consent: ConnectConsent };
/** `inPlace`: se abrió desde fuera de la pestaña (una habilidad, un hallazgo), y el aviso va en un toast. */
type ConnectTarget = { connector: AgentConnector; form: ConnectFormField[] | null; mode: "connect" | "reconnect"; inPlace?: boolean };

/**
 * Spec 047 (62.3; H11): «Conectar {X}» desde una habilidad o el fallo de una
 * prueba abre aquí mismo el diálogo de conectar, sin salir de la pantalla.
 * `connect` devuelve `false` si el conector no está en el catálogo del agente
 * (o ya lo usa): quien llama decide adónde ir.
 */
export type AgentConnectorsHandle = { connect: (slug: string) => boolean };

/**
 * La sección Conectores de un agente (spec 047, historia 21; T129; requisitos
 * 35.2, 35.3, 35.5 y 35.7): el catálogo que el partner puede usar, con lo que
 * piden las habilidades primero (el orden de la API), un buscador y la
 * categoría. Cada fila dice si el cliente lo tiene conectado y si este agente
 * lo usa.
 *
 * - **Sin conectar**: «Conectar» pide el permiso y autoriza. Si el cliente ya
 *   lo tenía autorizado, solo lo activa (35.4). Si es OAuth, se abre su
 *   autorización y la API lo activa al terminarla. Si pide una clave, se pide
 *   aquí y después se activa.
 * - **Conectado**: el permiso se elige en la fila, con «Sin usar en este
 *   agente» para quitarlo. Quitarlo pide confirmación y dice qué habilidades
 *   se quedan sin él (35.7).
 * - **Roto**: «Reconectar». Cada conexión tiene su página (36.1).
 *
 * Las acciones de las filas siguen la regla de los tres puntos: con más de dos
 * botones en la lista, cada fila las lleva en su «⋯» (`row-actions-rule.ts`).
 *
 * `connectors` en `undefined` se lee al montar (la lectura llama al catálogo
 * del proveedor y no frena el resto de la pantalla); en `null`, no se pudo leer.
 */
export function AgentConnectorsPanel({
  ref,
  refId,
  agentId,
  connectors: initial,
  canWrite,
  spec = null,
  onList,
  onConnected,
  actions: given = NO_ACTIONS,
}: {
  ref?: React.Ref<AgentConnectorsHandle>;
  refId: string;
  agentId: string;
  connectors?: AgentConnector[] | null;
  canWrite: boolean;
  /** El borrador, para decir qué habilidades lo piden antes de quitarlo. */
  spec?: AgentSpec | null;
  /** El catálogo cada vez que cambia: la pantalla sabe qué está conectado (H11). */
  onList?: (list: AgentConnector[]) => void;
  /** Un conector se conectó o se activó: las pruebas que lo usan quedan desactualizadas (62.3). */
  onConnected?: () => void;
  actions?: AgentConnectorsActions;
}) {
  const t = useT();
  const locale = useLocale();
  const actions = React.useMemo(() => ({ ...SERVER_ACTIONS, ...given }), [given]);
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [list, setList] = React.useState<AgentConnector[] | null | undefined>(initial);
  const [loading, setLoading] = React.useState(initial === undefined);
  const [query, setQuery] = React.useState("");
  // `null`: «Todos»; `CONNECTED_FILTER`: «Conectados»; si no, una categoría.
  const [category, setCategory] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState<Pending[]>([]);
  const [target, setTarget] = React.useState<ConnectTarget | null>(null);
  const [settingsOf, setSettingsOf] = React.useState<AgentConnector | null>(null);
  const [removing, setRemoving] = React.useState<AgentConnector | null>(null);
  const [rowError, setRowError] = React.useState<{ slug: string; text: string } | null>(null);
  const alive = React.useRef(true);
  React.useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  // La pantalla sabe qué conectores usa este agente (la línea de cada habilidad, H11).
  const onListRef = React.useRef(onList);
  React.useEffect(() => {
    onListRef.current = onList;
  });
  React.useEffect(() => {
    if (list) onListRef.current?.(list);
  }, [list]);

  React.useImperativeHandle(
    ref,
    () => ({
      connect: (slug: string) => {
        const c = list?.find((x) => x.slug === slug);
        if (!c || !canWrite || rowState(c) === "on") return false;
        setRowError(null);
        setTarget({ connector: c, form: null, mode: "connect", inPlace: true });
        return true;
      },
    }),
    [list, canWrite],
  );

  const load = React.useCallback(async () => {
    setLoading(true);
    const res = await actions.load(ids);
    if (!alive.current) return;
    setLoading(false);
    setList(res.ok ? res.data : null);
  }, [actions, ids]);

  // Sin datos del servidor: se leen al montar.
  const asked = React.useRef(initial !== undefined);
  React.useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    void load();
  }, [load]);

  function patch(slug: string, next: Partial<AgentConnector>) {
    setList((prev) => (prev ? prev.map((c) => (c.slug === slug ? { ...c, ...next } : c)) : prev));
  }

  function errorText(res: { status: number; code?: string | null }): string {
    if (res.status === 401 || res.status === 403) return t("common.forbidden");
    if (res.code === "connection_not_authorized" || res.code === "unknown_integration" || res.code === "invalid_settings") return t(`agentConn.error.${res.code}`);
    return t("agentConn.error.unknown");
  }

  async function remove(c: AgentConnector) {
    setBusy(c.slug);
    const res = await actions.remove({ ...ids, slug: c.slug });
    if (!alive.current) return;
    setBusy(null);
    setRemoving(null);
    if (!res.ok) return setRowError({ slug: c.slug, text: errorText(res) });
    patch(c.slug, { activation: null });
    const lost = [...res.data.skills.map(skillName), ...res.data.procedures];
    toast.success(lost.length ? t("agentConn.remove.affected", { name: c.name, list: lost.join(", ") }) : t("agentConn.remove.done", { name: c.name }));
  }

  /** «Reconectar» una conexión rota: la autorización de nuevo. Las activaciones se quedan. */
  async function reconnect(c: AgentConnector) {
    if (!c.connection) return;
    setRowError(null);
    setBusy(c.slug);
    const res = await actions.reconnect({ ref: refId, connection: c.connection.id });
    if (!alive.current) return;
    setBusy(null);
    if (res.ok) return void opened(c, res.data);
    // Una clave: se pide otra vez aquí.
    if (res.code === "authorize_with_form") return setTarget({ connector: c, form: null, mode: "reconnect" });
    setRowError({ slug: c.slug, text: errorText(res) });
  }

  function opened(c: AgentConnector, consent: ConnectConsent, inPlace = false) {
    actions.open(consent.signed_consent_url);
    setPending((prev) => [...prev.filter((p) => p.slug !== c.slug), { slug: c.slug, name: c.name, consent }]);
    // Desde fuera de la pestaña, el aviso con «Ya la terminé» va donde está la persona.
    if (inPlace) {
      toast(t("agentConn.connect.consent", { name: c.name }), {
        duration: Infinity,
        action: { label: t("agentConn.connect.finished"), onClick: () => void finished(c.slug) },
      });
    }
  }

  async function finished(slug: string) {
    setPending((prev) => prev.filter((p) => p.slug !== slug));
    await load();
    onConnected?.();
  }

  /** «Ajustes»: el permiso y los ajustes del catálogo, en una sola escritura (63.3). */
  async function saveSettings(c: AgentConnector, settings: ConnectorSettings, permission: ConnectorPermission | undefined) {
    return actions.activate({ ...ids, slug: c.slug, permission: permission ?? c.activation!.permission, settings });
  }

  if (list === undefined || (loading && list === null)) {
    return (
      // Con la forma de lo que llega (T218): el aviso donde va la introducción, el buscador y la tarjeta de filas.
      <div className="grid min-w-0 gap-4" aria-busy="true" data-slot="agent-connectors-loading">
        <p role="status" className="max-w-prose text-sm text-muted-foreground">
          {t("agentConn.loading")}
        </p>
        <Skeleton className="h-9 w-full sm:max-w-sm" />
        <div className="min-w-0 divide-y divide-border rounded-lg border border-border bg-card">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="flex min-w-0 items-center gap-3 px-4 py-4 sm:px-5">
              <Skeleton className="size-10 shrink-0" />
              <div className="grid min-w-0 flex-1 gap-2">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-4 w-3/4" />
              </div>
              <Skeleton className="h-8 w-24 shrink-0" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (list === null) {
    return (
      <Callout
        tone="danger"
        action={
          <Button size="sm" variant="outline" onClick={() => void load()}>
            {t("agentConn.retry")}
          </Button>
        }
      >
        {t("agentConn.error")}
      </Callout>
    );
  }

  const ordered = orderConnectors(list);
  const categories = categoriesOf(ordered);
  const counts = filterCounts(ordered);
  const visible = filterConnectors(ordered, { q: query, category });
  const filters: { key: string | null; label: string; count: number }[] = [
    { key: null, label: t("agentConn.filter.all"), count: counts.all },
    { key: CONNECTED_FILTER, label: t("agentConn.filter.connected"), count: counts.connected },
    ...categories.map((key) => ({ key, label: categoryLabel(t, key), count: counts.categories[key] ?? 0 })),
  ];

  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-connectors">
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("agentConn.intro")}</p>
      {!canWrite ? <p className="text-sm text-muted-foreground">{t("agentConn.readonly")}</p> : null}

      {list.length ? (
        // Como el prototipo (§9): el buscador sin etiqueta a la vista y el filtro segmentado de vidrio.
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
          <div role="search" className="relative w-full min-w-0 sm:max-w-sm">
            <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              className="pl-8"
              aria-label={t("agentConn.searchLabel")}
              placeholder={t("agentConn.searchLabel")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoComplete="off"
            />
          </div>
          <SegmentedControl
            type="pressed"
            aria-label={t("agentConn.category")}
            options={filters.map((f) => ({ value: f.key ?? ALL, label: f.label, count: f.count }))}
            value={category ?? ALL}
            onValueChange={(v) => setCategory(v === ALL ? null : v)}
          />
        </div>
      ) : null}

      {pending.map((p) => (
        <Callout
          key={p.slug}
          tone="info"
          action={
            <Button size="sm" variant="outline" onClick={() => void finished(p.slug)}>
              {t("agentConn.connect.finished")}
            </Button>
          }
        >
          <span className="grid gap-1">
            <span>{t("agentConn.connect.consent", { name: p.name })}</span>
            <a href={p.consent.signed_consent_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline underline-offset-4">
              {t("agentConn.connect.link", { when: formatDateTime(p.consent.expires_at, locale) })}
              <ExternalLink aria-hidden="true" className="size-3" />
            </a>
          </span>
        </Callout>
      ))}

      {!list.length ? (
        <p className="text-sm text-muted-foreground" data-slot="agent-connectors-empty">
          {t("agentConn.empty")}
        </p>
      ) : !visible.length ? (
        <div className="flex min-w-0 flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-4 text-sm">
          <p role="status" className="min-w-0 text-pretty text-muted-foreground">
            {query.trim() ? t("agentConn.noMatch", { q: query.trim() }) : t("agentConn.noResults")}
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setQuery("");
              setCategory(null);
            }}
          >
            {t("agentConn.clear")}
          </Button>
        </div>
      ) : (
        // Una sola tarjeta con filas divididas (prototipo §9; 63.3).
        <div className="min-w-0 rounded-lg border border-border bg-card">
          <ul aria-label={t("agentConn.list")} className="grid min-w-0 divide-y divide-border" data-slot="agent-connector-list">
            {visible.map((c) => (
              <ConnectorRow
                key={c.slug}
                connector={c}
                refId={refId}
                agentId={agentId}
                canWrite={canWrite}
                busy={busy === c.slug}
                error={rowError?.slug === c.slug ? rowError.text : null}
                onConnect={() => {
                  setRowError(null);
                  setTarget({ connector: c, form: null, mode: "connect" });
                }}
                onReconnect={() => void reconnect(c)}
                onSettings={() => setSettingsOf(c)}
                onRemove={() => setRemoving(c)}
              />
            ))}
          </ul>
        </div>
      )}

      {target ? (
        <ConnectDialog
          key={`${target.connector.slug}:${target.mode}`}
          refId={refId}
          target={target}
          onClose={() => setTarget(null)}
          actions={actions}
          ids={ids}
          onConsent={(consent) => opened(target.connector, consent, target.inPlace)}
          onDone={() => {
            void load();
            onConnected?.();
          }}
        />
      ) : null}

      {settingsOf?.activation ? (
        <SettingsDialog
          open
          onOpenChange={(o) => !o && setSettingsOf(null)}
          slug={settingsOf.slug}
          name={settingsOf.name}
          schema={settingsOf.settings_schema}
          settings={settingsOf.activation.settings}
          permission={settingsOf.activation.permission}
          pageHref={settingsOf.connection ? connectionHref(refId, settingsOf.connection.id, agentId) : null}
          save={(settings, permission) => saveSettings(settingsOf, settings, permission)}
          onSaved={(activation) => {
            const before = settingsOf.activation!.permission;
            patch(settingsOf.slug, { activation });
            toast.success(
              activation.permission !== before
                ? t("agentConn.permission.saved", { name: settingsOf.name, permission: permissionLabel(t, activation.permission) })
                : t("agentConn.settings.saved", { name: settingsOf.name }),
            );
          }}
        />
      ) : null}

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={removing ? t("agentConn.remove.title", { name: removing.name }) : ""}
        description={removing ? <RemoveBody spec={spec} slug={removing.slug} /> : null}
        confirmLabel={t("agentConn.remove")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={() => (removing ? remove(removing) : undefined)}
      />
    </div>
  );
}

/**
 * Una fila como el prototipo (§9; 63.3): el logo, el nombre con su categoría,
 * la nota —qué hace, si lo pide una habilidad y cómo se autoriza— y su acción:
 * «Conectar» (el principal si lo pide una habilidad), «Conectado» con
 * «Ajustes» y «Quitar», o «Reconectar» y su página si la conexión no está bien.
 */
function ConnectorRow({
  connector: c,
  refId,
  agentId,
  canWrite,
  busy,
  error,
  onConnect,
  onReconnect,
  onSettings,
  onRemove,
}: {
  connector: AgentConnector;
  refId: string;
  agentId: string;
  canWrite: boolean;
  busy: boolean;
  error: string | null;
  onConnect: () => void;
  onReconnect: () => void;
  onSettings: () => void;
  onRemove: () => void;
}) {
  const t = useT();
  const state = rowState(c);
  const desc = descriptionKey(c.slug);
  const kinds = rowActions(c, canWrite);
  const status = c.connection?.status ?? null;
  const note = [
    desc ? t(desc) : null,
    c.needed ? t("agentConn.note.needed") : null,
    state === "not_connected" ? authKindLabel(t, c.auth_kind) : null,
    state === "off" ? t("agentConn.state.off") : null,
    // Quien no puede abrir «Ajustes» ve el permiso como texto.
    state === "on" && !canWrite && c.activation ? permissionLabel(t, c.activation.permission) : null,
  ].filter(Boolean);
  return (
    <li className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-4 sm:px-5" data-slot="agent-connector" data-state={state} aria-busy={busy || undefined}>
      <ConnectorLogo refId={refId} slug={c.slug} name={c.name} logo={c.logo} />
      <div className="grid min-w-0 flex-1 basis-56 gap-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h3 className="min-w-0 font-medium break-words">{c.name}</h3>
          <StatusBadge tone="muted" dot={false} className="h-5 text-xs">
            {categoryLabel(t, categoryOf(c))}
          </StatusBadge>
          {state === "other" ? (
            <StatusBadge tone={isBroken(status) ? "danger" : "warn"} data-slot="connector-state">
              {t(connectorStatusKey(status))}
            </StatusBadge>
          ) : null}
        </div>
        {note.length ? <p className="text-sm text-pretty text-muted-foreground">{note.join(" · ")}</p> : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {state === "on" ? (
          <StatusBadge tone="positive" dot={false} data-slot="connector-state">
            <span className="inline-flex items-center gap-1">
              <CircleCheck aria-hidden="true" className="size-3 text-status-positive-text" />
              {t("agentConn.connected")}
            </span>
          </StatusBadge>
        ) : null}
        {kinds.map((kind) => {
          switch (kind) {
            case "connect":
              return (
                <Button key={kind} size="sm" variant={c.needed ? "default" : "outline"} disabled={busy} onClick={onConnect} aria-label={t("agentConn.connect.named", { name: c.name })}>
                  {t("agentConn.connect")}
                </Button>
              );
            case "reconnect":
              return (
                <Button key={kind} size="sm" disabled={busy} loading={busy} onClick={onReconnect} aria-label={t("agentConn.reconnect.named", { name: c.name })}>
                  {t("agentConn.reconnect")}
                </Button>
              );
            case "settings":
              return (
                <Button key={kind} size="sm" variant="ghost" disabled={busy} onClick={onSettings} aria-label={t("agentConn.settings.named", { name: c.name })}>
                  {t("agentConn.settings")}
                </Button>
              );
            case "remove":
              return (
                <Button key={kind} size="sm" variant="ghost" disabled={busy} loading={busy} onClick={onRemove} aria-label={t("agentConn.remove.named", { name: c.name })}>
                  {t("agentConn.remove.short")}
                </Button>
              );
            case "page":
              return c.connection ? (
                <Link
                  key={kind}
                  href={connectionHref(refId, c.connection.id, agentId)}
                  aria-label={t("agentConn.page.named", { name: c.name })}
                  className={buttonVariants({ size: "sm", variant: "outline" })}
                >
                  {t("agentConn.page")}
                </Link>
              ) : null;
          }
        })}
      </div>
      {error ? (
        <p role="alert" className="basis-full text-sm text-pretty text-destructive">
          {error}
        </p>
      ) : null}
    </li>
  );
}

/** Lo que dice el diálogo de quitar: qué deja de poder hacer este agente (35.7). */
function RemoveBody({ spec, slug }: { spec: AgentSpec | null; slug: string }) {
  const t = useT();
  const skills = skillsUsing(spec, slug).map((s) => skillName(s.key));
  return (
    <span className="grid gap-2">
      <span>{t("agentConn.remove.body")}</span>
      <span>{skills.length ? t("agentConn.remove.skills", { list: skills.join(", ") }) : t("agentConn.remove.none")}</span>
    </span>
  );
}

/**
 * «Conectar» (35.3): el permiso primero; después, lo que pida el servicio. Si
 * ya está autorizado para el cliente, la API lo activa sin más (35.4). Si es
 * OAuth, se abre su ventana y la API lo activa al terminar. Si pide una clave,
 * se pide aquí, se guarda con el alta de siempre y después se activa.
 */
function ConnectDialog({
  refId,
  target,
  onClose,
  actions,
  ids,
  onConsent,
  onDone,
}: {
  refId: string;
  target: ConnectTarget;
  onClose: () => void;
  actions: Required<AgentConnectorsActions>;
  ids: Ids;
  onConsent: (consent: ConnectConsent) => void;
  onDone: () => void;
}) {
  const t = useT();
  const c = target.connector;
  const [permission, setPermission] = React.useState<ConnectorPermission>(c.activation?.permission ?? "read");
  const [form, setForm] = React.useState<ConnectFormField[] | null>(target.form);
  const [needsForm, setNeedsForm] = React.useState(target.mode === "reconnect");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function connect(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const res = await actions.connect({ ...ids, slug: c.slug, permission });
    setBusy(false);
    if (res.ok) {
      if ("signed_consent_url" in res.data) {
        onConsent(res.data);
      } else {
        toast.success(t("agentConn.connect.done", { name: c.name }));
        onDone();
      }
      return onClose();
    }
    if (res.code === "authorize_with_form") {
      const fields = Array.isArray(res.info?.form) ? (res.info.form as ConnectFormField[]) : null;
      setForm(fields);
      setNeedsForm(true);
      return;
    }
    setError(res.status === 401 || res.status === 403 ? t("common.forbidden") : t("agentConn.error.unknown"));
  }

  async function saveKey(values: Record<string, string>) {
    if (!form?.length) return;
    setError(null);
    setBusy(true);
    const saved = await actions.saveKey({ ref: refId, slug: c.slug, ...splitCredentials(form, values) });
    if (!saved.ok) {
      setBusy(false);
      return setError(saved.status === 401 || saved.status === 403 ? t("common.forbidden") : t("agentConn.error.unknown"));
    }
    if (saved.data.last_sync?.status === "error" && saved.data.last_sync.reason === "auth_rejected") {
      setBusy(false);
      return setError(t("agentConn.connect.rejected", { name: c.name }));
    }
    // Conectar activa con el permiso elegido; reconectar deja las activaciones como estaban.
    if (target.mode === "connect") {
      const res = await actions.activate({ ...ids, slug: c.slug, permission, settings: c.activation?.settings ?? {} });
      if (!res.ok) {
        setBusy(false);
        return setError(t("agentConn.error.unknown"));
      }
    }
    setBusy(false);
    toast.success(t("agentConn.connect.done", { name: c.name }));
    onDone();
    onClose();
  }

  const permissionField = <PermissionRadios legend={t("agentConn.connect.permission")} value={permission} onChange={setPermission} disabled={busy} />;

  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("agentConn.connect.title", { name: c.name })}</DialogTitle>
          <DialogDescription>
            {!needsForm ? t("agentConn.connect.body") : form?.length ? t("agentConn.connect.form", { name: c.name }) : t("agentConn.connect.noForm", { name: c.name })}
          </DialogDescription>
        </DialogHeader>
        {!needsForm ? (
          <form className="grid min-w-0 gap-4" onSubmit={(e) => void connect(e)} aria-busy={busy}>
            {permissionField}
            {error ? (
              <p role="alert" className="text-sm text-destructive text-pretty">
                {error}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" loading={busy}>
                {t("agentConn.connect.submit")}
              </Button>
            </DialogFooter>
          </form>
        ) : form?.length ? (
          <CredentialsForm
            slug={c.slug}
            fields={form}
            busy={busy}
            error={error}
            submitLabel={t("agentConn.connect.form.submit")}
            onSubmit={(values) => void saveKey(values)}
            onCancel={onClose}
          />
        ) : (
          <div className="grid min-w-0 gap-4">
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                {t("common.close")}
              </Button>
              <Button nativeButton={false} render={<Link href={`/clients/${encodeURIComponent(refId)}/integrations`} />}>
                {t("agentConn.connect.goClient")}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
