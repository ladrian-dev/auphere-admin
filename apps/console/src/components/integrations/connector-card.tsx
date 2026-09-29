"use client";

import { ExternalLink, MoreHorizontal, Plus } from "lucide-react";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
  Label,
  StatusBadge,
  StatusDot,
  cn,
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
import { messages, type MessageKey } from "@/i18n/messages";
import { actionErrorText } from "@/lib/action-error";
import type { ConnectorOut, ConsentOut, LastSync } from "@/lib/backend/agent-tools-types";

/**
 * Un conector (spec 017 R4; rehecho con el owner el 2026-09-28).
 *
 * **Se lee de un vistazo: icono, nombre, para qué sirve, y un botón.** Antes
 * era un nombre, cuatro datos sueltos en la misma línea y hasta cinco
 * botones en fila; había que leerla entera para saber si estaba conectada.
 * Ahora la tarjeta tiene la forma de un directorio de aplicaciones, que es
 * lo que es.
 *
 * Lo que decide:
 *
 * - **El estado no depende de una insignia.** Un punto en la esquina del
 *   icono y una palabra en la línea de abajo lo dicen; la insignia se
 *   reserva para cuando hay algo que explicar —roto, pausado, caducado—,
 *   que es cuando hacen falta palabras. Quien no distingue el color lee la
 *   palabra; quien no lee la línea ve el punto.
 * - **Una sola acción a la vista.** Conectar es un `+`, como en cualquier
 *   directorio. Lo demás —sincronizar, pausar, reanudar, desconectar— vive
 *   en «Más», igual que en la cabecera de la ficha. Ninguna se ha perdido.
 * - **Un conector roto pide palabras, no un icono.** Ahí la acción vuelve a
 *   ser un botón con texto: «Reconectar» tiene que poder leerse.
 * - **Dice qué desbloquea**, en número de habilidades. Es lo que convierte
 *   «conectar WooCommerce» de tarea administrativa en decisión fácil (R4.2).
 * - **Desconectar sigue pidiendo confirmación.** Corta habilidades que están
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

  const broken = status === "error" || status === "revoked" || status === "expired";
  const actions = !canWrite ? null : !installed ? (
    // Sin conectar: el `+` de cualquier directorio. Lleva su nombre
    // accesible porque un icono solo no dice a qué conector pertenece.
    <Button size="icon-sm" onClick={connect} disabled={pending} aria-label={t("connectors.connect.aria", { name })}>
      <Plus aria-hidden="true" />
    </Button>
  ) : (
    <span className="flex shrink-0 items-center gap-2">
      {/* Roto: la salida se lee, no se adivina. */}
      {broken ? (
        <Button size="xs" onClick={connect} disabled={pending}>
          {t("connectors.reconnect")}
        </Button>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button size="icon-sm" variant="ghost" disabled={pending} aria-label={t("connectors.more", { name })}>
              <MoreHorizontal aria-hidden="true" />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          {!connected && !broken ? (
            <DropdownMenuItem onClick={connect}>{t("connectors.reconnect")}</DropdownMenuItem>
          ) : null}
          {!apiKey ? <DropdownMenuItem onClick={sync}>{t("connectors.sync")}</DropdownMenuItem> : null}
          {connected ? (
            <DropdownMenuItem onClick={() => changeStatus("pause")}>{t("connectors.pause")}</DropdownMenuItem>
          ) : null}
          {status === "paused" ? (
            <DropdownMenuItem onClick={() => changeStatus("resume")}>{t("connectors.resume")}</DropdownMenuItem>
          ) : null}
          <DropdownMenuItem variant="destructive" onClick={() => setDisconnecting(true)}>
            {t("connectors.disconnect")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </span>
  );

  return (
    <CardShell name={name} refId={refId} connector={connector} pending={pending} actions={actions}>
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

/**
 * El armazón común: icono, nombre, para qué sirve, la acción, y debajo lo
 * que se sabe de él.
 */
function CardShell({
  name,
  refId,
  connector,
  pending,
  actions,
  children,
}: {
  name: string;
  refId: string;
  connector: ConnectorOut;
  pending: boolean;
  /** Lo que se puede hacer con él: un `+`, un «Más», o nada. */
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const t = useT();
  const locale = useLocale();
  const unlocks = connector.tools_total;
  const status = connector.status;
  const connected = status === "connected";
  const broken = status === "error" || status === "revoked" || status === "expired";
  // La insignia se reserva para lo que necesita explicación. «Conectado» y
  // «sin conectar» ya los dicen el punto y la palabra de la línea de abajo;
  // repetirlos en una insignia es ruido que compite con el que sí importa.
  const badge = connector.installed && !connected;

  return (
    <li
      className={cn(
        "flex min-w-0 flex-col gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10",
        // Lo roto se ve antes de leerlo, también en la tarjeta entera.
        broken && "ring-destructive/30",
      )}
      aria-busy={pending}
    >
      <div className="flex min-w-0 items-start gap-3">
        <ConnectorIcon connector={connector} refId={refId} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h3 className="min-w-0 truncate font-medium" title={name}>
            {name}
          </h3>
          {/* Para qué sirve, que es lo que decide si merece la pena
              conectarlo. La API no lo trae; el copy es nuestro. */}
          <p className="text-sm text-pretty text-muted-foreground">{t(descKey(connector.slug))}</p>
        </div>
        {actions}
      </div>

      {/* Lo que se sabe de él: el estado en palabras, qué desbloquea, cuántas
          están encendidas y cuándo se sincronizó. Todo en una línea, en
          gris, porque se consulta — no se decide con ello. */}
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <StatusDot tone={connectorTone(status)} />
          {connected
            ? t("connectors.state.connected")
            : connector.installed
              ? t(connectorStatusKey(status))
              : t("connectors.state.notConnected")}
        </span>
        {badge ? (
          <StatusBadge tone={connectorTone(status)}>{t(connectorStatusKey(status))}</StatusBadge>
        ) : null}
        {unlocks > 0 ? (
          <Link
            href={`/clients/${encodeURIComponent(refId)}/capabilities`}
            className="underline underline-offset-4"
          >
            {unlocks === 1 ? t("int.unlocksOne") : t("int.unlocks", { n: unlocks })}
          </Link>
        ) : null}
        {connector.tools_enabled > 0 ? (
          <span className="tabular-nums">
            {t("connectors.tools", { on: connector.tools_enabled, total: connector.tools_total })}
          </span>
        ) : null}
        {connector.last_synced_at ? (
          <span className="tabular-nums">
            {t("connectors.lastSync")}: {formatDateTime(connector.last_synced_at, locale)}
          </span>
        ) : null}
      </div>
      {children}
    </li>
  );
}

/** La descripción del conector, si la tenemos escrita. Se comprueba contra
 *  el diccionario como ya hacen `statusKey` y `roleKey`: un conector nuevo
 *  del catálogo cae en la frase de reserva en vez de pintar su clave. */
function descKey(slug: string): MessageKey {
  const key = `connectors.desc.${slug}` as MessageKey;
  return key in messages ? key : "connectors.desc.fallback";
}

/**
 * El icono de la aplicación, con su estado en la esquina.
 *
 * **El logotipo se pide a nuestro propio origen**, no al proveedor. Pedírselo
 * al proveedor es lo que se hacía y no funcionaba nunca: la consola publica
 * `img-src 'self' data: blob:`, así que el navegador bloqueaba todas las
 * imágenes de otros dominios y pintaba el icono de imagen rota. La ruta
 * `/api/connector-logo/…` las sirve desde aquí, y de paso el navegador del
 * partner deja de contarle a Meta o a WordPress qué conectores mira.
 *
 * Cuando el catálogo no trae logotipo, la inicial sobre un cuadro tintado; un
 * hueco gris no distingue una tarjeta de otra.
 */
function ConnectorIcon({ connector, refId }: { connector: ConnectorOut; refId: string }) {
  const inicial = connector.display_name.trim().charAt(0).toUpperCase();
  return (
    <span data-slot="connector-icon" className="relative shrink-0">
      <span className="flex size-10 items-center justify-center overflow-hidden rounded-md bg-muted ring-1 ring-foreground/10">
        {connector.logo_url ? (
          /* `next/image` exige declarar cada dominio remoto uno a uno, y el
             catálogo puede traer cualquiera; además estas ya vienen por
             nuestra propia ruta, así que no hay nada que optimizar. */
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`/api/connector-logo/${encodeURIComponent(refId)}/${encodeURIComponent(connector.slug)}`}
            alt=""
            loading="lazy"
            className="size-10 object-contain"
          />
        ) : (
          <span aria-hidden="true" className="text-sm font-medium text-muted-foreground">
            {inicial}
          </span>
        )}
      </span>
      {/* Solo cuando hay algo que decir: un punto sobre un conector sin
          conectar sería un estado inventado. */}
      {connector.installed ? (
        <StatusDot
          tone={connectorTone(connector.status)}
          className="absolute -right-1 -bottom-1 ring-2 ring-card"
        />
      ) : null}
    </span>
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
  // La misma gramática que el resto: sin enlazar, un `+`; enlazado, «Más».
  // Su acción es distinta —una URL pública, no credenciales— pero eso no es
  // razón para que la tarjeta se lea distinta.
  const actions = !canWrite ? null : !linked ? (
    <Button
      size="icon-sm"
      onClick={() => setOpen(true)}
      disabled={pending}
      aria-label={t("connectors.agendapro.link")}
    >
      <Plus aria-hidden="true" />
    </Button>
  ) : (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button size="icon-sm" variant="ghost" disabled={pending} aria-label={t("connectors.more", { name })}>
            <MoreHorizontal aria-hidden="true" />
          </Button>
        }
      />
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setOpen(true)}>{t("connectors.agendapro.relink")}</DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onClick={() => setUnlinking(true)}>
          {t("connectors.agendapro.unlink")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <CardShell name={name} refId={refId} connector={connector} pending={pending} actions={actions}>
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
