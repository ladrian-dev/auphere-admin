"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
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
  Input,
  Label,
  StatusBadge,
  formatDateTime,
} from "@nexus/ui";

import {
  connectApiKeyAction,
  connectorStatusAction,
  setAgendaProUrlAction,
  startConsentAction,
  syncConnectorAction,
} from "@/app/(console)/clients/[ref]/integrations/actions";
import {
  connectorStatusKey,
  connectorTone,
  credentialFieldLabel,
  lastSyncKey,
  splitCredentials,
} from "@/components/agent-tools/lib";
import { useLocale, useT } from "@/i18n/client";
import { messages } from "@/i18n/messages";
import { actionErrorText } from "@/lib/action-error";
import type { ConnectorOut, ConsentOut, LastSync } from "@/lib/backend/agent-tools-types";

/**
 * Una integración (spec 017, R4). Viene de la cabecera de conector que vivía
 * dentro de la pantalla de Herramientas: mismas cuatro formas de conectar,
 * mismos diálogos, misma validación. Lo que cambia es dónde está y qué dice
 * de sí misma.
 *
 * Lo que esta tarjeta decide:
 *
 * - **Dice qué desbloquea**, en número de capacidades. Es lo que convierte
 *   «conectar WooCommerce» de tarea administrativa en decisión fácil (R4.2).
 * - **Lo que necesita atención se ve sin leer**: el estado va en su insignia
 *   y la acción que lo arregla es el botón primario.
 * - **Desconectar sigue pidiendo confirmación.** Corta capacidades que están
 *   funcionando, y eso no puede pasar por un clic distraído.
 */
export function ConnectorCard({
  refId,
  connector,
  canWrite,
}: {
  refId: string;
  connector: ConnectorOut;
  canWrite: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [consent, setConsent] = React.useState<ConsentOut | null>(null);
  const [disconnecting, setDisconnecting] = React.useState(false);
  const [apiKeyOpen, setApiKeyOpen] = React.useState(false);
  // Spec 016 (R7.3): cómo fue el sync que acaba de correr con la conexión. No
  // está en la lista (la API lo dice una vez); vive aquí hasta el refresco.
  const [lastSync, setLastSync] = React.useState<LastSync | null>(null);

  const { slug, status } = connector;
  const name = connector.display_name;
  const apiKey = connector.auth_kind === "api_key";
  const installed = connector.installed;
  const connected = status === "connected";
  const syncKey = lastSyncKey(lastSync);

  function connect() {
    if (apiKey) return void setApiKeyOpen(true);
    startTransition(async () => {
      const res = await startConsentAction({ ref: refId, slug });
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      const win = window.open(res.data.signed_consent_url, "_blank", "noopener,noreferrer");
      if (win) toast.success(t("connectors.consent.opened", { name }));
      else setConsent(res.data);
      router.refresh();
    });
  }
  function sync() {
    startTransition(async () => {
      const res = await syncConnectorAction({ ref: refId, slug });
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      toast.success(
        t("connectors.synced", {
          name,
          added: res.data.added.length,
          deprecated: res.data.deprecated.length,
          unchanged: res.data.unchanged_count,
        }),
      );
      router.refresh();
    });
  }
  function changeStatus(op: "pause" | "resume" | "disconnect") {
    startTransition(async () => {
      const res = await connectorStatusAction({ ref: refId, slug, op });
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      toast.success(
        t(
          op === "pause"
            ? "connectors.paused"
            : op === "resume"
              ? "connectors.resumed"
              : "connectors.disconnected",
          { name },
        ),
      );
      setDisconnecting(false);
      router.refresh();
    });
  }

  if (connector.auth_kind === "public_url") {
    // Spec 016 (R6): AgendaPro se enlaza con la página pública de su agenda.
    // Ni credenciales, ni consentimiento, ni sincronizar: una URL y «desenlazar».
    return <PublicLinkCard refId={refId} connector={connector} canWrite={canWrite} />;
  }

  return (
    <CardShell name={name} refId={refId} connector={connector} pending={pending}>
      {canWrite ? (
        <span className="flex flex-wrap gap-2">
          {!connected ? (
            <Button size="xs" onClick={connect} disabled={pending}>
              {installed ? t("connectors.reconnect") : t("connectors.connect")}
            </Button>
          ) : null}
          {installed && !apiKey ? (
            <Button size="xs" variant="outline" onClick={sync} disabled={pending}>
              {t("connectors.sync")}
            </Button>
          ) : null}
          {connected ? (
            <Button size="xs" variant="outline" onClick={() => changeStatus("pause")} disabled={pending}>
              {t("connectors.pause")}
            </Button>
          ) : null}
          {status === "paused" ? (
            <Button size="xs" variant="outline" onClick={() => changeStatus("resume")} disabled={pending}>
              {t("connectors.resume")}
            </Button>
          ) : null}
          {installed ? (
            <Button size="xs" variant="destructive" onClick={() => setDisconnecting(true)} disabled={pending}>
              {t("connectors.disconnect")}
            </Button>
          ) : null}
        </span>
      ) : null}

      {syncKey ? (
        <p className="flex flex-wrap items-center gap-2 text-xs" role="status">
          <span
            className={
              syncKey === "connectors.lastSync.ok" ? "text-muted-foreground" : "text-destructive"
            }
          >
            {t(syncKey, { n: connector.tools_total })}
          </span>
          {syncKey === "connectors.lastSync.provider_unavailable" ? (
            <Button size="xs" variant="outline" onClick={sync} disabled={pending}>
              {t("connectors.lastSync.retry")}
            </Button>
          ) : null}
          {syncKey === "connectors.lastSync.auth_rejected" ? (
            <Button size="xs" variant="outline" onClick={() => setApiKeyOpen(true)} disabled={pending}>
              {t("connectors.lastSync.fix")}
            </Button>
          ) : null}
        </p>
      ) : null}

      {consent ? (
        <p className="text-xs text-muted-foreground">
          {t("connectors.consent.blocked")}{" "}
          <a
            href={consent.signed_consent_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 underline underline-offset-4"
          >
            {t("connectors.consent.link", { when: formatDateTime(consent.expires_at, locale) })}
            <ExternalLink className="size-3" aria-hidden="true" />
          </a>
        </p>
      ) : null}

      <ConfirmDialog
        open={disconnecting}
        onOpenChange={setDisconnecting}
        title={t("connectors.disconnect.title", { name })}
        description={t("connectors.disconnect.body")}
        confirmLabel={t("connectors.disconnect")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={() => changeStatus("disconnect")}
      />
      <ApiKeyDialog
        refId={refId}
        connector={connector}
        open={apiKeyOpen}
        onOpenChange={setApiKeyOpen}
        onConnected={setLastSync}
      />
    </CardShell>
  );
}

/** La cabecera común: nombre, estado, qué desbloquea y cuándo se sincronizó. */
function CardShell({
  name,
  refId,
  connector,
  pending,
  children,
}: {
  name: string;
  refId: string;
  connector: ConnectorOut;
  pending: boolean;
  children?: React.ReactNode;
}) {
  const t = useT();
  const locale = useLocale();
  const unlocks = connector.tools_total;
  return (
    <li
      className="flex min-w-0 flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10"
      aria-busy={pending}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
        <h3 className="min-w-0 truncate font-medium" title={name}>
          {name}
        </h3>
        <StatusBadge tone={connectorTone(connector.status)}>
          {t(connectorStatusKey(connector.status))}
        </StatusBadge>
        {/* R4.2: qué desbloquea, que es lo que convierte la tarea en decisión.
            Sin catálogo sincronizado todavía no se puede contar, y decir «0
            capacidades» sonaría a que no sirve para nada. */}
        {unlocks > 0 ? (
          <Link
            href={`/clients/${encodeURIComponent(refId)}/capabilities`}
            className="text-xs text-muted-foreground underline underline-offset-4"
          >
            {unlocks === 1 ? t("int.unlocksOne") : t("int.unlocks", { n: unlocks })}
          </Link>
        ) : null}
        {connector.tools_enabled > 0 ? (
          <span className="text-xs text-muted-foreground tabular-nums">
            {t("connectors.tools", { on: connector.tools_enabled, total: connector.tools_total })}
          </span>
        ) : null}
        {connector.last_synced_at ? (
          <span className="text-xs text-muted-foreground tabular-nums">
            {t("connectors.lastSync")}: {formatDateTime(connector.last_synced_at, locale)}
          </span>
        ) : null}
      </div>
      {children}
    </li>
  );
}

/**
 * Spec 016 (R6): AgendaPro — «Enlazar la agenda». Lo que el runtime necesita
 * es la página pública de reservas; nada secreto se pide, nunca.
 */
function PublicLinkCard({
  refId,
  connector,
  canWrite,
}: {
  refId: string;
  connector: ConnectorOut;
  canWrite: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [open, setOpen] = React.useState(false);
  const [unlinking, setUnlinking] = React.useState(false);
  const [value, setValue] = React.useState(connector.public_url ?? "");
  const [error, setError] = React.useState<string | null>(null);
  const linked = Boolean(connector.public_url);
  const name = connector.display_name;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const url = value.trim();
    if (!/^https:\/\/([a-z0-9-]+\.)*agendapro\.com(\/|$)/i.test(url))
      return void setError(t("connectors.agendapro.invalid"));
    setError(null);
    startTransition(async () => {
      const res = await setAgendaProUrlAction({ ref: refId, public_url: url });
      if (!res.ok)
        return void setError(
          res.code === "invalid_url" ? t("connectors.agendapro.invalid") : actionErrorText(res, t),
        );
      toast.success(t("connectors.agendapro.linked"));
      setOpen(false);
      router.refresh();
    });
  }
  function unlink() {
    startTransition(async () => {
      const res = await setAgendaProUrlAction({ ref: refId, public_url: null });
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      toast.success(t("connectors.agendapro.unlinked"));
      setUnlinking(false);
      setValue("");
      router.refresh();
    });
  }

  const fieldId = `agendapro-url-${refId}`;
  return (
    <CardShell name={name} refId={refId} connector={connector} pending={pending}>
      {linked ? (
        <a
          href={connector.public_url ?? undefined}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-w-0 items-center gap-1 text-xs text-muted-foreground underline underline-offset-4"
        >
          <span className="truncate">{connector.public_url}</span>
          <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
        </a>
      ) : null}
      <p className="text-xs text-pretty text-muted-foreground">{t("connectors.agendapro.body")}</p>
      {canWrite ? (
        <span className="flex flex-wrap gap-2">
          <Button size="xs" onClick={() => setOpen(true)} disabled={pending}>
            {linked ? t("connectors.agendapro.relink") : t("connectors.agendapro.link")}
          </Button>
          {linked ? (
            <Button size="xs" variant="destructive" onClick={() => setUnlinking(true)} disabled={pending}>
              {t("connectors.agendapro.unlink")}
            </Button>
          ) : null}
        </span>
      ) : null}

      <Dialog open={open} onOpenChange={(o) => !pending && setOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("connectors.agendapro.title")}</DialogTitle>
            <DialogDescription>{t("connectors.agendapro.help")}</DialogDescription>
          </DialogHeader>
          <form className="grid gap-3" onSubmit={submit} noValidate aria-busy={pending}>
            <div className="grid gap-1">
              <Label htmlFor={fieldId}>{t("connectors.agendapro.field")}</Label>
              <Input
                id={fieldId}
                type="url"
                inputMode="url"
                autoComplete="off"
                spellCheck={false}
                placeholder={t("connectors.agendapro.placeholder")}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? `${fieldId}-err` : undefined}
                required
              />
              {error ? (
                <p id={`${fieldId}-err`} className="text-xs text-destructive" aria-live="polite">
                  {error}
                </p>
              ) : null}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={pending}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={pending}>
                {t("connectors.agendapro.link")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={unlinking}
        onOpenChange={setUnlinking}
        title={t("connectors.agendapro.unlink.title", { name })}
        description={t("connectors.agendapro.unlink.body")}
        confirmLabel={t("connectors.agendapro.unlink")}
        cancelLabel={t("common.cancel")}
        destructive
        onConfirm={unlink}
      />
    </CardShell>
  );
}

function ApiKeyDialog({
  refId,
  connector,
  open,
  onOpenChange,
  onConnected,
}: {
  refId: string;
  connector: ConnectorOut;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onConnected?: (sync: LastSync | null) => void;
}) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const fields = connector.credentials_form;

  function close(o: boolean) {
    if (!o) {
      setValues({});
      setErrors({});
    }
    onOpenChange(o);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const missing: Record<string, string> = {};
    for (const f of fields)
      if (f.required !== false && !(values[f.field] ?? "").trim())
        missing[f.field] = t("connectors.apiKey.required");
    setErrors(missing);
    if (Object.keys(missing).length) return;
    const body = splitCredentials(fields, values);
    startTransition(async () => {
      const res = await connectApiKeyAction({ ref: refId, slug: connector.slug, ...body });
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      // Spec 016 (R7.1/R7.3): guardar ES conectar; la API sincroniza en la
      // misma llamada y dice cómo fue. No hay un segundo clic.
      const sync = res.data.last_sync ?? null;
      onConnected?.(sync);
      const name = connector.display_name;
      if (sync?.status === "error" && sync.reason === "auth_rejected")
        toast.error(t("connectors.apiKey.rejected", { name }));
      else if (sync?.status === "error")
        toast.warning(t("connectors.apiKey.savedButNotSynced", { name }));
      else toast.success(t("connectors.apiKey.connected", { name }));
      close(false);
      router.refresh();
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && close(o)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("connectors.apiKey.title", { name: connector.display_name })}</DialogTitle>
          <DialogDescription>{t("connectors.apiKey.body")}</DialogDescription>
        </DialogHeader>
        {fields.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("connectors.apiKey.noForm")}</p>
        ) : (
          <form className="grid gap-3" onSubmit={submit} noValidate aria-busy={pending}>
            {fields.map((f) => {
              const id = `cred-${connector.slug}-${f.field}`;
              return (
                <div key={f.field} className="grid gap-1">
                  <Label htmlFor={id}>
                    {credentialFieldLabel(connector.slug, f, messages, (k) =>
                      t(k as Parameters<typeof t>[0]),
                    )}
                  </Label>
                  <Input
                    id={id}
                    type={f.secret ? "password" : "text"}
                    autoComplete={f.secret ? "new-password" : "off"}
                    spellCheck={false}
                    placeholder={f.placeholder}
                    value={values[f.field] ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [f.field]: e.target.value }))}
                    aria-invalid={errors[f.field] ? true : undefined}
                    aria-describedby={errors[f.field] ? `${id}-err` : undefined}
                    required={f.required !== false}
                  />
                  {errors[f.field] ? (
                    <p id={`${id}-err`} className="text-xs text-destructive" aria-live="polite">
                      {errors[f.field]}
                    </p>
                  ) : null}
                </div>
              );
            })}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)} disabled={pending}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={pending}>
                {t("connectors.apiKey.submit")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
