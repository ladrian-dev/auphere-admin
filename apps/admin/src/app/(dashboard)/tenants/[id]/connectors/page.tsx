import Link from "next/link";
import { notFound } from "next/navigation";

import { ConnectorAuthBadge } from "@/components/brand/connector-auth-badge";
import { ConnectorLogo } from "@/components/brand/connector-logo";
import { Eyebrow } from "@/components/brand/eyebrow";
import { StatusDot } from "@/components/brand/status-dot";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  backend,
  type Connector,
  type ConnectorToolOverride,
  type TenantConnector,
  type TenantConnectorStatus,
} from "@/lib/backend";
import { relativeTime } from "@/lib/format";

import {
  DisconnectButton,
  InitiateConsentButton,
  ReissueConsentButton,
  SyncButton,
} from "./connector-actions";
import { AgendaProSetupDialog, WhatsAppSetupDialog } from "./setup-wizards";

const STATUS_TONE: Record<
  TenantConnectorStatus,
  "positive" | "warning" | "danger" | "muted"
> = {
  connected: "positive",
  partial: "warning",
  needs_reauth: "danger",
  pending: "warning",
  disconnected: "muted",
  error: "danger",
};

const STATUS_LABEL: Record<TenantConnectorStatus, string> = {
  connected: "Conectado",
  partial: "Parcial",
  needs_reauth: "Requiere re-auth",
  pending: "Esperando consent",
  disconnected: "Desconectado",
  error: "Error",
};

export default async function TenantConnectorsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const tenant = await backend.getTenant(id);
  if (!tenant) notFound();

  const [installed, catalog, overrides] = await Promise.all([
    backend.listTenantConnectors(id),
    backend.listConnectors({ status: "available" }),
    backend.listConnectorToolOverrides(id),
  ]);

  const installedBySlug = new Map(installed.map((c) => [c.connector_slug, c]));
  const catalogBySlug = new Map(catalog.map((c) => [c.slug, c]));
  const overridesByTool = new Map(overrides.map((o) => [o.tool_name, o]));
  const notInstalled = catalog.filter(
    (c) => !installedBySlug.has(c.slug),
  );

  return (
    <div className="grid gap-6">
      <section className="flex flex-col gap-3">
        <Eyebrow>Conectados</Eyebrow>
        {installed.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              Este tenant todavía no tiene connectors. Empezá conectando el
              canal de mensajería que va a usar el agente y después sumá los
              que habiliten las tools que vas a activar.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3">
            {installed.map((tc) => (
              <InstalledConnectorCard
                key={tc.id}
                tenantId={id}
                tc={tc}
                catalogEntry={catalogBySlug.get(tc.connector_slug) ?? null}
                ownerPhone={tenant.owner_phone}
                overrides={overridesByTool}
              />
            ))}
          </div>
        )}
      </section>

      {notInstalled.length > 0 ? (
        <section className="flex flex-col gap-3">
          <Eyebrow>Disponibles</Eyebrow>
          <p className="text-sm text-muted-foreground -mt-2">
            Connectors del catálogo que este tenant todavía no instaló. Para
            los OAuth, &quot;Conectar&quot; manda un link de consent al owner;
            para los manuales abre un wizard.
          </p>
          <div className="grid gap-3">
            {notInstalled.map((c) => (
              <AvailableConnectorCard
                key={c.id}
                tenantId={id}
                connector={c}
                ownerPhone={tenant.owner_phone}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function InstalledConnectorCard({
  tenantId,
  tc,
  catalogEntry,
  ownerPhone,
  overrides,
}: {
  tenantId: string;
  tc: TenantConnector;
  catalogEntry: Connector | null;
  ownerPhone: string | null;
  overrides: Map<string, ConnectorToolOverride>;
}) {
  const isComposio = tc.connector_auth_kind === "oauth_composio";
  const isPending = tc.status === "pending";
  const isNeedsReauth = tc.status === "needs_reauth";
  return (
    <Card>
      <CardHeader className="flex flex-col gap-1">
        <Eyebrow>{tc.connector_category}</Eyebrow>
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
          <div className="flex flex-row items-center gap-3 min-w-0">
            {catalogEntry ? <ConnectorLogo connector={catalogEntry} /> : null}
            <div className="flex flex-col gap-1 min-w-0">
            <CardTitle className="flex items-center gap-2 flex-wrap">
              {tc.connector_display_name}
              <ConnectorAuthBadge kind={tc.connector_auth_kind} />
            </CardTitle>
            <CardDescription className="flex items-center gap-2">
              <StatusDot tone={STATUS_TONE[tc.status]} />
              <span>{STATUS_LABEL[tc.status]}</span>
              {tc.connected_at ? (
                <span className="text-xs text-muted-foreground">
                  · conectado {relativeTime(tc.connected_at)}
                </span>
              ) : null}
            </CardDescription>
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            {isPending || isNeedsReauth ? (
              <ReissueConsentButton
                tenantId={tenantId}
                slug={tc.connector_slug}
                displayName={tc.connector_display_name}
              />
            ) : null}
            {isComposio && tc.status === "connected" ? (
              <SyncButton
                tenantId={tenantId}
                slug={tc.connector_slug}
                displayName={tc.connector_display_name}
              />
            ) : null}
            {tc.status !== "disconnected" ? (
              <DisconnectButton
                tenantId={tenantId}
                slug={tc.connector_slug}
                displayName={tc.connector_display_name}
              />
            ) : (
              <InitiateConsentButton
                tenantId={tenantId}
                slug={tc.connector_slug}
                displayName={tc.connector_display_name}
                ownerPhone={ownerPhone}
              />
            )}
          </div>
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="grid gap-4 pt-6 text-sm md:grid-cols-3">
        <Stat
          label="Última sincronización"
          value={
            tc.last_synced_at ? (
              <span>{relativeTime(tc.last_synced_at)}</span>
            ) : (
              <span className="text-muted-foreground">—</span>
            )
          }
          hint={
            isComposio
              ? "Click Sincronizar para refrescar tools/list."
              : "Los tools son estáticos."
          }
        />
        <Stat
          label="Scopes concedidos"
          value={
            tc.scopes_granted.length > 0 ? (
              <span className="font-mono text-xs">
                {tc.scopes_granted.length}
              </span>
            ) : (
              <span className="text-muted-foreground">—</span>
            )
          }
          hint={
            tc.scopes_granted.length > 0
              ? tc.scopes_granted.slice(0, 3).join(", ") +
                (tc.scopes_granted.length > 3 ? "…" : "")
              : "Sin scopes OAuth en este connector"
          }
        />
        <Stat
          label="Overrides"
          value={
            overrides.size > 0 ? (
              <span className="tabular-nums">{overrides.size}</span>
            ) : (
              <span className="text-muted-foreground">0</span>
            )
          }
          hint="Cantidad de tools con gating override custom para este tenant."
        />
      </CardContent>
      {isPending && tc.consent_token_expires_at ? (
        <CardContent className="pt-0 text-xs text-muted-foreground">
          Link de consent expira {relativeTime(tc.consent_token_expires_at)}. Si
          el owner no clickeó todavía, reenvía con el botón de arriba.
        </CardContent>
      ) : null}
    </Card>
  );
}

function AvailableConnectorCard({
  tenantId,
  connector,
  ownerPhone,
}: {
  tenantId: string;
  connector: Connector;
  ownerPhone: string | null;
}) {
  const isComposio = connector.auth_kind === "oauth_composio";
  return (
    <Card>
      <CardHeader className="flex flex-col gap-1">
        <Eyebrow>{connector.category}</Eyebrow>
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
          <div className="flex flex-row items-center gap-3 min-w-0">
            <ConnectorLogo connector={connector} />
            <div className="flex flex-col gap-1 min-w-0">
            <CardTitle className="flex items-center gap-2 flex-wrap">
              {connector.display_name}
              <ConnectorAuthBadge kind={connector.auth_kind} />
            </CardTitle>
            <CardDescription>
              {connector.auth_kind === "oauth_composio"
                ? "OAuth multi-tenant. El owner aprueba en su navegador."
                : connector.auth_kind === "browser_credentials"
                  ? "Credenciales del owner que el operador automatiza por browser."
                  : connector.auth_kind === "webhook_manual"
                    ? "El operador pega los IDs del proveedor en el wizard."
                    : "API key configurada en secrets."}
            </CardDescription>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="flex gap-2 flex-wrap">
              {isComposio ? (
                <InitiateConsentButton
                  tenantId={tenantId}
                  slug={connector.slug}
                  displayName={connector.display_name}
                  ownerPhone={ownerPhone}
                />
              ) : connector.slug === "whatsapp_ycloud" ? (
                <WhatsAppSetupDialog
                  tenantId={tenantId}
                  alreadyConnected={false}
                />
              ) : connector.slug === "agendapro" ? (
                <AgendaProSetupDialog
                  tenantId={tenantId}
                  alreadyConnected={false}
                />
              ) : (
                <Badge variant="outline" className="text-xs">
                  Setup manual
                </Badge>
              )}
            </div>
            {isComposio && !ownerPhone ? (
              <p className="text-[11px] text-muted-foreground">
                Necesita owner_phone.{" "}
                <Link
                  href={`/tenants/${tenantId}`}
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  Configurar →
                </Link>
              </p>
            ) : null}
          </div>
        </div>
      </CardHeader>
    </Card>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span
        className="text-[10px] font-mono uppercase text-muted-foreground"
        style={{ letterSpacing: "var(--tracking-eyebrow)" }}
      >
        {label}
      </span>
      <div className="text-base">{value}</div>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
