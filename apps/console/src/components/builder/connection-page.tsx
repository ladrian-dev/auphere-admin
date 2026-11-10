"use client";

import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  ConfirmDialog,
  DescriptionList,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  StatusBadge,
  formatDateTime,
} from "@nexus/ui";

import {
  connectionPageAction,
  disconnectConnectionAction,
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
  ConnectConsent,
  ConnectionPage,
  ConnectionUser,
  ConnectorPermission,
  ConnectorSettings,
  DisconnectImpact,
  Disconnected,
} from "@/lib/backend/agent-connectors-types";
import type { ConnectorOut } from "@/lib/backend/agent-tools-types";

import { skillName, type Result } from "./builder-model";
import { agentConnectorsHref, permissionLabel, settingFields, settingsSummary } from "./connector-model";
import { ConnectorLogo, CredentialsForm, PermissionSelect, SettingsDialog, permissionHint } from "./connector-parts";

type ConnIds = { ref: string; connection: string };
type AgentIds = { ref: string; agent: string };
export type ConnectionPageActions = {
  reload?: (body: ConnIds) => Promise<Result<ConnectionPage>>;
  activate?: (body: AgentIds & { slug: string; permission: ConnectorPermission; settings: ConnectorSettings }) => Promise<Result<Activation>>;
  remove?: (body: AgentIds & { slug: string }) => Promise<Result<AffectedSkills>>;
  reconnect?: (body: ConnIds) => Promise<Result<ConnectConsent>>;
  disconnect?: (body: ConnIds & { confirm: boolean }) => Promise<Result<Disconnected>>;
  saveKey?: (body: { ref: string; slug: string; secrets: Record<string, string>; endpoint_meta: Record<string, unknown> }) => Promise<Result<ConnectorOut>>;
  open?: (url: string) => void;
};

const SERVER_ACTIONS: Required<ConnectionPageActions> = {
  reload: (body) => connectionPageAction(body),
  activate: (body) => setActivationAction(body),
  remove: (body) => removeActivationAction(body),
  reconnect: (body) => reconnectConnectionAction(body),
  disconnect: (body) => disconnectConnectionAction(body),
  saveKey: (body) => connectApiKeyAction(body),
  open: (url) => void window.open(url, "_blank", "noopener,noreferrer"),
};
const NO_ACTIONS: ConnectionPageActions = {};

/**
 * La página de cada conector conectado (spec 047, historia 21; T129;
 * requisitos 36.1, 36.3 y 36.4): la cuenta, el estado con la hora de la última
 * comprobación, los agentes de este cliente que lo usan con su permiso y sus
 * ajustes, «Reconectar» y «Desconectar para todos».
 *
 * - «Hay que volver a autorizar» se dice arriba, con «Reconectar» (36.3).
 * - El permiso de cada agente se cambia en su fila; «Sin usar» lo quita, con
 *   confirmación. Sus ajustes, en «Ajustes» (36.2).
 * - «Desconectar para todos» primero pregunta a la API a quién afecta y lo
 *   lista; solo con la confirmación desconecta (36.4).
 *
 * Quien no tiene `agents:write` lo ve todo sin botones (§V).
 */
export function ConnectionPageView({
  refId,
  page: initial,
  connector = null,
  fromAgent = null,
  canWrite,
  actions: given = NO_ACTIONS,
}: {
  refId: string;
  page: ConnectionPage;
  /** El conector en el catálogo del cliente: cómo se autoriza y su formulario de clave. */
  connector?: ConnectorOut | null;
  /** El agente desde el que se llegó: la página sabe volver a él. */
  fromAgent?: string | null;
  canWrite: boolean;
  actions?: ConnectionPageActions;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const actions = React.useMemo(() => ({ ...SERVER_ACTIONS, ...given }), [given]);
  const ids = React.useMemo(() => ({ ref: refId, connection: initial.id }), [refId, initial.id]);
  const [page, setPage] = React.useState(initial);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [rowError, setRowError] = React.useState<{ agent: string; text: string } | null>(null);
  const [settingsOf, setSettingsOf] = React.useState<ConnectionUser | null>(null);
  const [removing, setRemoving] = React.useState<ConnectionUser | null>(null);
  const [consent, setConsent] = React.useState<ConnectConsent | null>(null);
  const [keyOpen, setKeyOpen] = React.useState(false);
  const [keyError, setKeyError] = React.useState<string | null>(null);
  const [impact, setImpact] = React.useState<DisconnectImpact[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const fields = React.useMemo(() => settingFields(page.settings_schema), [page.settings_schema]);
  const back = fromAgent ? agentConnectorsHref(refId, fromAgent) : `/clients/${encodeURIComponent(refId)}/integrations`;
  const name = page.name;

  async function reload() {
    const res = await actions.reload(ids);
    if (res.ok) setPage(res.data);
  }

  function setUser(agentId: string, next: Partial<ConnectionUser> | null) {
    setPage((prev) => ({
      ...prev,
      agents: next === null ? prev.agents.filter((a) => a.agent_id !== agentId) : prev.agents.map((a) => (a.agent_id === agentId ? { ...a, ...next } : a)),
    }));
  }

  function failText(res: { status: number; code?: string | null }): string {
    if (res.status === 401 || res.status === 403) return t("common.forbidden");
    if (res.code === "connection_not_authorized" || res.code === "unknown_integration") return t(`agentConn.error.${res.code}`);
    return t("agentConn.error.unknown");
  }

  async function choose(user: ConnectionUser, next: ConnectorPermission | null) {
    setRowError(null);
    if (next === null) return setRemoving(user);
    if (next === user.permission) return;
    setBusy(user.agent_id);
    const res = await actions.activate({ ref: refId, agent: user.agent_id, slug: page.integration, permission: next, settings: user.settings });
    setBusy(null);
    if (!res.ok) return setRowError({ agent: user.agent_id, text: failText(res) });
    setUser(user.agent_id, { permission: res.data.permission, settings: res.data.settings });
    toast.success(t("agentConn.permission.saved", { name: user.name, permission: permissionLabel(t, res.data.permission) }));
  }

  async function remove(user: ConnectionUser) {
    setBusy(user.agent_id);
    const res = await actions.remove({ ref: refId, agent: user.agent_id, slug: page.integration });
    setBusy(null);
    setRemoving(null);
    if (!res.ok) return setRowError({ agent: user.agent_id, text: failText(res) });
    setUser(user.agent_id, null);
    const lost = [...res.data.skills.map(skillName), ...res.data.procedures];
    toast.success(
      lost.length
        ? t("connPage.removed.affected", { name, agent: user.name, list: lost.join(", ") })
        : t("connPage.removed", { name, agent: user.name }),
    );
  }

  async function reconnect() {
    setError(null);
    setBusy("reconnect");
    const res = await actions.reconnect(ids);
    setBusy(null);
    if (res.ok) {
      actions.open(res.data.signed_consent_url);
      setConsent(res.data);
      return;
    }
    // Una clave o un formulario: se pide aquí con el del catálogo.
    if (res.code === "authorize_with_form") return setKeyOpen(true);
    setError(failText(res));
  }

  async function saveKey(values: Record<string, string>) {
    if (!connector?.credentials_form.length) return;
    setKeyError(null);
    setBusy("key");
    const res = await actions.saveKey({ ref: refId, slug: page.integration, ...splitCredentials(connector.credentials_form, values) });
    setBusy(null);
    if (!res.ok) return setKeyError(failText(res));
    if (res.data.last_sync?.status === "error" && res.data.last_sync.reason === "auth_rejected") return setKeyError(t("agentConn.connect.rejected", { name }));
    setKeyOpen(false);
    toast.success(t("connectors.apiKey.connected", { name }));
    await reload();
  }

  /** «Desconectar para todos»: primero, a quién afecta (36.4). */
  async function askDisconnect() {
    setError(null);
    setBusy("disconnect");
    const res = await actions.disconnect({ ...ids, confirm: false });
    setBusy(null);
    if (res.ok) return done();
    if (res.code === "confirm_required") {
      const affected = res.info?.affected;
      setImpact(Array.isArray(affected) ? (affected as DisconnectImpact[]) : []);
      return;
    }
    setError(failText(res));
  }

  async function confirmDisconnect() {
    const res = await actions.disconnect({ ...ids, confirm: true });
    if (!res.ok) {
      setImpact(null);
      return setError(failText(res));
    }
    setImpact(null);
    done();
  }

  function done() {
    toast.success(t("connPage.disconnect.done", { name }));
    router.push(back);
  }

  const status = page.needs_reauth ? "needs_reauth" : page.status;
  // La regla de los tres puntos: más de dos botones en la lista, o más de uno en una fila, al «⋯».
  const perRow = 1 + (canWrite && fields.length ? 1 : 0) + (canWrite ? 1 : 0);
  const menu = foldsIntoMenu(perRow * page.agents.length) || perRow > 1;
  const keyFields = connector?.credentials_form ?? [];

  return (
    <div className="grid min-w-0 gap-6" data-slot="connection-page">
      <Link href={back} className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
        <ArrowLeft aria-hidden="true" className="size-4" />
        {fromAgent ? t("connPage.back.agent") : t("connPage.back.client")}
      </Link>

      <header className="flex min-w-0 flex-wrap items-start gap-3">
        <ConnectorLogo refId={refId} slug={page.integration} name={name} logo={page.logo} />
        <div className="grid min-w-0 flex-1 gap-1">
          <h2 className="min-w-0 text-xl font-semibold text-balance break-words">{name}</h2>
          <span className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
            <StatusBadge tone={connectorTone(status)} data-slot="connection-state">
              {t(connectorStatusKey(status))}
            </StatusBadge>
          </span>
        </div>
        {canWrite ? (
          <div className="flex min-w-0 flex-wrap gap-2">
            <Button variant="outline" onClick={() => void reconnect()} loading={busy === "reconnect"} disabled={busy !== null}>
              {t("connPage.reconnect")}
            </Button>
            <Button variant="destructive" onClick={() => void askDisconnect()} loading={busy === "disconnect"} disabled={busy !== null}>
              {t("connPage.disconnect")}
            </Button>
          </div>
        ) : null}
      </header>

      {!canWrite ? <p className="text-sm text-muted-foreground">{t("connPage.readonly")}</p> : null}
      {page.needs_reauth ? (
        <Callout
          tone="warning"
          action={
            canWrite ? (
              <Button size="sm" onClick={() => void reconnect()} disabled={busy !== null}>
                {t("connPage.reconnect")}
              </Button>
            ) : undefined
          }
        >
          {t("connPage.reauth", { name })}
        </Callout>
      ) : null}
      {consent ? (
        <Callout tone="info">
          <span className="grid gap-1">
            <span>{t("connPage.reconnect.opened", { name })}</span>
            <a href={consent.signed_consent_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline underline-offset-4">
              {t("agentConn.connect.link", { when: formatDateTime(consent.expires_at, locale) })}
              <ExternalLink aria-hidden="true" className="size-3" />
            </a>
          </span>
        </Callout>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {error}
        </p>
      ) : null}

      <section aria-labelledby="conexion-detalle" className="grid min-w-0 gap-3 rounded-md border border-border bg-card p-4 sm:p-6">
        <h3 id="conexion-detalle" className="text-base font-semibold">
          {t("connPage.details")}
        </h3>
        <DescriptionList
          layout="inline"
          items={[
            { key: "account", term: t("connPage.account"), detail: page.account ?? <span className="text-muted-foreground">{t("connPage.account.none")}</span>, truncate: Boolean(page.account) },
            { key: "state", term: t("connPage.state"), detail: t(connectorStatusKey(status)) },
            { key: "since", term: t("connPage.connectedAt"), detail: page.connected_at ? formatDateTime(page.connected_at, locale) : "—" },
            {
              key: "checked",
              term: t("connPage.checkedAt"),
              detail: page.last_checked_at ? <span className="tabular-nums">{formatDateTime(page.last_checked_at, locale)}</span> : t("connPage.checkedAt.never"),
            },
          ]}
        />
      </section>

      <section aria-labelledby="conexion-agentes" className="grid min-w-0 gap-3 rounded-md border border-border bg-card p-4 sm:p-6">
        <h3 id="conexion-agentes" className="text-base font-semibold">
          {t("connPage.agents")}
        </h3>
        {page.agents.length ? (
          <ul aria-labelledby="conexion-agentes" className="grid min-w-0 gap-3" data-slot="connection-agents">
            {page.agents.map((user) => {
              const summary = settingsSummary(t, page.integration, fields, user.settings);
              const rowActions: RowAction[] = [
                { label: t("connPage.openAgent"), href: agentConnectorsHref(refId, user.agent_id), primary: true },
                ...(canWrite && fields.length ? [{ label: t("agentConn.settings"), onSelect: () => setSettingsOf(user) }] : []),
                ...(canWrite ? [{ label: t("agentConn.remove"), onSelect: () => setRemoving(user) }] : []),
              ];
              return (
                <li key={user.agent_id} className="grid min-w-0 gap-2 rounded-md border border-border p-3" data-slot="connection-agent" aria-busy={busy === user.agent_id || undefined}>
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <h4 className="min-w-0 font-medium break-words">{user.name}</h4>
                    <RowActions actions={rowActions} menu={menu} ariaLabel={t("connPage.agents.actions", { name: user.name })} />
                  </div>
                  <div className="grid min-w-0 gap-1 sm:max-w-sm">
                    {canWrite ? (
                      <PermissionSelect
                        label={t("connPage.agents.permissionOf", { name, agent: user.name })}
                        value={user.permission}
                        allowOff
                        busy={busy === user.agent_id}
                        onChange={(next) => void choose(user, next)}
                      />
                    ) : (
                      <span className="text-sm">{permissionLabel(t, user.permission)}</span>
                    )}
                    <span className="text-xs text-pretty text-muted-foreground">{permissionHint(t, user.permission)}</span>
                  </div>
                  {fields.length ? (
                    summary.length ? (
                      <ul aria-label={t("connPage.agents.settings")} className="grid min-w-0 gap-1 text-xs text-muted-foreground">
                        {summary.map((line) => (
                          <li key={line} className="break-words">
                            {line}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-muted-foreground">{t("agentConn.settings.none")}</p>
                    )
                  ) : null}
                  {rowError?.agent === user.agent_id ? (
                    <p role="alert" className="text-sm text-destructive text-pretty">
                      {rowError.text}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-pretty text-muted-foreground" data-slot="connection-agents-empty">
            {t("connPage.agents.empty")}
          </p>
        )}
      </section>

      {settingsOf ? (
        <SettingsDialog
          open
          onOpenChange={(o) => !o && setSettingsOf(null)}
          slug={page.integration}
          name={`${name} · ${settingsOf.name}`}
          schema={page.settings_schema}
          settings={settingsOf.settings}
          save={(settings) => actions.activate({ ref: refId, agent: settingsOf.agent_id, slug: page.integration, permission: settingsOf.permission, settings })}
          onSaved={(activation) => {
            setUser(settingsOf.agent_id, { permission: activation.permission, settings: activation.settings });
            toast.success(t("agentConn.settings.saved", { name }));
          }}
        />
      ) : null}

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={removing ? t("connPage.remove.title", { name, agent: removing.name }) : ""}
        description={t("agentConn.remove.body")}
        confirmLabel={t("agentConn.remove")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={() => (removing ? remove(removing) : undefined)}
      />

      <ConfirmDialog
        open={impact !== null}
        onOpenChange={(o) => !o && setImpact(null)}
        title={t("connPage.disconnect.title", { name })}
        description={<DisconnectBody impact={impact ?? []} />}
        confirmLabel={t("connPage.disconnect")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={confirmDisconnect}
      />

      <Dialog open={keyOpen} onOpenChange={(o) => busy !== "key" && setKeyOpen(o)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t("agentConn.connect.title", { name })}</DialogTitle>
            <DialogDescription>{keyFields.length ? t("agentConn.connect.form", { name }) : t("agentConn.connect.noForm", { name })}</DialogDescription>
          </DialogHeader>
          {keyFields.length ? (
            <CredentialsForm
              slug={page.integration}
              fields={keyFields}
              busy={busy === "key"}
              error={keyError}
              submitLabel={t("agentConn.connect.form.submit")}
              onSubmit={(values) => void saveKey(values)}
              onCancel={() => setKeyOpen(false)}
            />
          ) : (
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setKeyOpen(false)}>
                {t("common.close")}
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** A quién afecta «Desconectar para todos»: cada agente y lo que pierde (36.4). */
function DisconnectBody({ impact }: { impact: DisconnectImpact[] }) {
  const t = useT();
  return (
    <span className="grid gap-2">
      <span>{t("connPage.disconnect.body")}</span>
      {impact.length ? (
        <>
          <span>{t("connPage.disconnect.affected")}</span>
          <span className="grid gap-1" data-slot="disconnect-impact">
            {impact.map((a) => {
              const lost = [...a.skills.map(skillName), ...a.procedures];
              return (
                <span key={a.agent_id} className="block">
                  {lost.length ? t("connPage.disconnect.agentSkills", { name: a.name, list: lost.join(", ") }) : t("connPage.disconnect.agentNoSkills", { name: a.name })}
                </span>
              );
            })}
          </span>
        </>
      ) : (
        <span>{t("connPage.disconnect.nobody")}</span>
      )}
    </span>
  );
}
