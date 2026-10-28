"use client";

import { ExternalLink, Search } from "lucide-react";
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
  Label,
  NativeSelect,
  Skeleton,
  StatusBadge,
  StatusDot,
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
import { connectorStatusKey, connectorTone, splitCredentials } from "@/components/agent-tools/lib";
import { RowActions, type RowAction } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
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
import { CONNECTOR_PERMISSIONS } from "@/lib/backend/agent-connectors-types";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";
import type { AgentSpec } from "@/lib/backend/builder-types";

import { skillName, type Result } from "./builder-model";
import { ConnectorLogo, CredentialsForm, PermissionSelect, SettingsDialog, permissionHint } from "./connector-parts";
import {
  authKindLabel,
  categoriesOf,
  categoryLabel,
  categoryOf,
  connectionHref,
  descriptionKey,
  filterConnectors,
  isBroken,
  permissionLabel,
  rowActions,
  rowState,
  skillsUsing,
  type RowActionKind,
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

/** Una autorización abierta en otra ventana: el enlace por si el navegador la bloqueó. */
type Pending = { slug: string; name: string; consent: ConnectConsent };
type ConnectTarget = { connector: AgentConnector; form: ConnectFormField[] | null; mode: "connect" | "reconnect" };

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
  refId,
  agentId,
  connectors: initial,
  canWrite,
  spec = null,
  actions: given = NO_ACTIONS,
}: {
  refId: string;
  agentId: string;
  connectors?: AgentConnector[] | null;
  canWrite: boolean;
  /** El borrador, para decir qué habilidades lo piden antes de quitarlo. */
  spec?: AgentSpec | null;
  actions?: AgentConnectorsActions;
}) {
  const t = useT();
  const locale = useLocale();
  const actions = React.useMemo(() => ({ ...SERVER_ACTIONS, ...given }), [given]);
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [list, setList] = React.useState<AgentConnector[] | null | undefined>(initial);
  const [loading, setLoading] = React.useState(initial === undefined);
  const [query, setQuery] = React.useState("");
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
  const searchId = React.useId();
  const categoryId = React.useId();

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

  /** El permiso de la fila cambió: activar, cambiar o (con confirmación) quitar. */
  async function choose(c: AgentConnector, next: ConnectorPermission | null) {
    setRowError(null);
    if (next === null) {
      if (c.activation) setRemoving(c);
      return;
    }
    if (c.activation?.permission === next) return;
    setBusy(c.slug);
    const res = await actions.activate({ ...ids, slug: c.slug, permission: next, settings: c.activation?.settings ?? {} });
    if (!alive.current) return;
    setBusy(null);
    if (!res.ok) return setRowError({ slug: c.slug, text: errorText(res) });
    patch(c.slug, { activation: res.data });
    const permission = permissionLabel(t, res.data.permission);
    toast.success(c.activation ? t("agentConn.permission.saved", { name: c.name, permission }) : t("agentConn.activated", { name: c.name, permission }));
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

  function opened(c: AgentConnector, consent: ConnectConsent) {
    actions.open(consent.signed_consent_url);
    setPending((prev) => [...prev.filter((p) => p.slug !== c.slug), { slug: c.slug, name: c.name, consent }]);
  }

  async function finished(slug: string) {
    setPending((prev) => prev.filter((p) => p.slug !== slug));
    await load();
  }

  if (list === undefined || (loading && list === null)) {
    return (
      <div className="grid min-w-0 gap-3" aria-busy="true" data-slot="agent-connectors-loading">
        <p role="status" className="text-sm text-muted-foreground">
          {t("agentConn.loading")}
        </p>
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
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

  const categories = categoriesOf(list);
  const visible = filterConnectors(list, { q: query, category });
  // La regla de los tres puntos: más de dos botones en la lista, o más de uno
  // en una fila, y cada fila lleva los suyos en su «⋯».
  const perRow = visible.map((c) => rowActions(c, canWrite).length);
  const menu = foldsIntoMenu(perRow.reduce((n, k) => n + k, 0)) || perRow.some((n) => n > 1);

  const actionOf = (c: AgentConnector, kind: RowActionKind, primary: boolean): RowAction => {
    switch (kind) {
      case "connect":
        return { label: t("agentConn.connect"), primary, onSelect: () => setTarget({ connector: c, form: null, mode: "connect" }) };
      case "reconnect":
        return { label: t("agentConn.reconnect"), primary, onSelect: () => void reconnect(c) };
      case "page":
        return { label: t("agentConn.page"), primary, href: connectionHref(refId, c.connection!.id, agentId) };
      case "settings":
        return { label: t("agentConn.settings"), primary, onSelect: () => setSettingsOf(c) };
      case "remove":
        return { label: t("agentConn.remove"), primary, onSelect: () => setRemoving(c) };
    }
  };

  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-connectors">
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("agentConn.intro")}</p>
      {!canWrite ? <p className="text-sm text-muted-foreground">{t("agentConn.readonly")}</p> : null}

      {list.length ? (
        <div className="flex min-w-0 flex-wrap items-end gap-3" role="search" aria-label={t("agentConn.search")}>
          <div className="grid min-w-0 flex-1 basis-56 gap-1">
            <Label htmlFor={searchId}>{t("agentConn.search")}</Label>
            <div className="relative min-w-0">
              <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id={searchId}
                type="search"
                className="pl-8"
                placeholder={t("agentConn.search.placeholder")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoComplete="off"
              />
            </div>
          </div>
          {categories.length > 1 ? (
            <div className="grid min-w-0 gap-1">
              <Label htmlFor={categoryId}>{t("agentConn.category")}</Label>
              <NativeSelect id={categoryId} value={category ?? ""} onChange={(e) => setCategory(e.target.value || null)}>
                <option value="">{t("agentConn.category.all")}</option>
                {categories.map((key) => (
                  <option key={key} value={key}>
                    {categoryLabel(t, key)}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ) : null}
        </div>
      ) : null}

      {list.length ? (
        <p className="text-xs text-muted-foreground tabular-nums" role="status" aria-live="polite">
          {t("agentConn.count", { shown: visible.length, total: list.length })}
        </p>
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
        <div className="flex min-w-0 flex-wrap items-center gap-3 text-sm">
          <p className="text-muted-foreground">{t("agentConn.noResults")}</p>
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
        <ul aria-label={t("agentConn.list")} className="grid min-w-0 gap-3" data-slot="agent-connector-list">
          {visible.map((c) => {
            const state = rowState(c);
            const rowActionsList = rowActions(c, canWrite).map((k, i) => actionOf(c, k, i === 0));
            const desc = descriptionKey(c.slug);
            return (
              <li key={c.slug} className="grid min-w-0 gap-3 rounded-md border border-border p-3" data-slot="agent-connector" data-state={state} aria-busy={busy === c.slug || undefined}>
                <div className="flex min-w-0 items-start gap-3">
                  <ConnectorLogo refId={refId} slug={c.slug} name={c.name} logo={c.logo} />
                  <div className="grid min-w-0 flex-1 gap-1">
                    <h3 className="min-w-0 font-medium break-words">{c.name}</h3>
                    {desc ? <p className="text-sm text-pretty text-muted-foreground">{t(desc)}</p> : null}
                    <p className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <StateLine connector={c} />
                      {c.needed ? <StatusBadge tone="info">{t("agentConn.needed")}</StatusBadge> : null}
                      <span>{categoryLabel(t, categoryOf(c))}</span>
                      <span>{authKindLabel(t, c.auth_kind)}</span>
                    </p>
                  </div>
                  {rowActionsList.length ? (
                    <div className="shrink-0">
                      {menu ? (
                        <RowActions actions={rowActionsList} menu ariaLabel={t("agentConn.actions", { name: c.name })} />
                      ) : (
                        <SingleAction action={rowActionsList[0]!} name={c.name} />
                      )}
                    </div>
                  ) : null}
                </div>
                {state === "on" || state === "off" ? (
                  <div className="grid min-w-0 gap-1 sm:max-w-sm">
                    {canWrite ? (
                      <PermissionSelect
                        label={t("agentConn.permission", { name: c.name })}
                        value={c.activation?.permission ?? null}
                        allowOff
                        busy={busy === c.slug}
                        onChange={(next) => void choose(c, next)}
                      />
                    ) : (
                      <span className="text-sm">{c.activation ? permissionLabel(t, c.activation.permission) : t("agentConn.permission.off")}</span>
                    )}
                    {c.activation ? <span className="text-xs text-pretty text-muted-foreground">{permissionHint(t, c.activation.permission)}</span> : null}
                  </div>
                ) : null}
                {rowError?.slug === c.slug ? (
                  <p role="alert" className="text-sm text-destructive text-pretty">
                    {rowError.text}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {target ? (
        <ConnectDialog
          key={`${target.connector.slug}:${target.mode}`}
          refId={refId}
          target={target}
          onClose={() => setTarget(null)}
          actions={actions}
          ids={ids}
          onConsent={(consent) => opened(target.connector, consent)}
          onDone={() => void load()}
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
          save={(settings) => actions.activate({ ...ids, slug: settingsOf.slug, permission: settingsOf.activation!.permission, settings })}
          onSaved={(activation) => {
            patch(settingsOf.slug, { activation });
            toast.success(t("agentConn.settings.saved", { name: settingsOf.name }));
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

/** Una sola acción a la vista: lleva el nombre del conector para quien no ve la fila. */
function SingleAction({ action, name }: { action: RowAction; name: string }) {
  const label = `${action.label} ${name}`;
  return action.href ? (
    <Button size="sm" variant="outline" nativeButton={false} render={<Link href={action.href} aria-label={label} />}>
      {action.label}
    </Button>
  ) : (
    <Button size="sm" onClick={action.onSelect} disabled={action.disabled} aria-label={label}>
      {action.label}
    </Button>
  );
}

/** «Conectado» o el estado de la conexión del cliente, con su punto: la palabra lo dice sin el color. */
function StateLine({ connector: c }: { connector: AgentConnector }) {
  const t = useT();
  const state = rowState(c);
  const status = c.connection?.status ?? null;
  const text =
    state === "not_connected"
      ? t("agentConn.state.notConnected")
      : state === "on"
        ? t("agentConn.state.on")
        : state === "off"
          ? t("agentConn.state.off")
          : t(connectorStatusKey(status));
  const tone = state === "not_connected" || state === "off" ? "muted" : state === "on" ? "positive" : connectorTone(status);
  return (
    <span className="inline-flex items-center gap-2" data-slot="connector-state">
      <StatusDot tone={tone} />
      {isBroken(status) ? <StatusBadge tone="danger">{text}</StatusBadge> : text}
    </span>
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
  const formId = React.useId();

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

  const permissionField = (
    <fieldset className="grid min-w-0 gap-2">
      <legend className="mb-1 text-sm font-medium">{t("agentConn.connect.permission")}</legend>
      {CONNECTOR_PERMISSIONS.map((p) => {
        const id = `${formId}-${p}`;
        return (
          <label key={p} htmlFor={id} className="flex min-w-0 cursor-pointer items-start gap-2 rounded-md border border-border p-2 text-sm has-[:checked]:border-primary">
            <input
              id={id}
              type="radio"
              name={`${formId}-permission`}
              value={p}
              checked={permission === p}
              onChange={() => setPermission(p)}
              className="mt-1 accent-primary"
              disabled={busy}
            />
            <span className="grid min-w-0 gap-1">
              <span className="font-medium">{permissionLabel(t, p)}</span>
              <span className="text-xs text-pretty text-muted-foreground">{permissionHint(t, p)}</span>
            </span>
          </label>
        );
      })}
    </fieldset>
  );

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
