"use client";

import { AlertTriangle, RotateCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  Alert,
  AlertDescription,
  Button,
  HelpHint,
  Meter,
  Metric,
  Section,
  StatusBadge,
  StatusDot,
  formatNumber,
} from "@nexus/ui";

import { creditTone } from "../credit-tone";
import { SettingsForm } from "./settings-form";
import { useLocale, useT } from "@/i18n/client";
import { can, type Role } from "@/lib/permissions";

/**
 * El Resumen del cliente (spec 018, R1/R2).
 *
 * **Contesta cuatro preguntas; no enseña todos los datos.** El owner pidió un
 * resumen completo, y un resumen que lo enseña todo deja de resumir: vuelve a
 * ser una pantalla que hay que leer entera. Así que cada bloque responde una
 * pregunta con su cifra, y el detalle está a un clic en la pantalla que ya lo
 * tenía.
 *
 * Las tres reglas que lo hacen honesto:
 *
 * - **Sin actividad no es cero.** Un cliente recién creado dice que todavía
 *   no hay datos. Un cero grande se lee como una caída.
 * - **Una lectura caída no tumba la pantalla.** Son cuatro fuentes; si una
 *   falla, lo dice en su bloque, ofrece reintentar y las otras siguen. Por
 *   eso se piden por separado y no en una llamada que las junte.
 * - **Quien no puede escribir no ve controles muertos**, y lee las cifras
 *   igual.
 */

/** Una lectura que puede no haber llegado. `null` = este rol no la pide. */
export type Block<T> = { ok: true; data: T } | { ok: false };

export type ConnectedItem = {
  key: string;
  name: string;
  status: string;
  detail?: string | null;
  /** Cuántas habilidades desbloquea, si es un conector. */
  unlocks?: number | null;
  /** Cuántos quedan sin conectar, para la línea final. */
};

export type SummaryProps = {
  refId: string;
  role: Role;
  client: {
    name: string;
    timezone: string;
    status: string;
    sector: string | null;
    health: {
      ready: boolean;
      agent_version: number | null;
      whatsapp_connected: boolean;
      display_phone_number?: string | null;
    };
    quota: { cap: number; remaining: number } | null;
  };
  usage: Block<{ units: number; projected: number; basisDays: number; daysInMonth: number }>;
  /** `null` cuando el rol no puede leer conversaciones: el bloque no existe. */
  conversations: Block<{ conversations: number; escalated: number; failed_messages: number }> | null;
  connected: Block<ConnectedItem[]>;
  /** Los que están sin conectar y no se listan uno a uno. */
  notConnected?: number;
};

export function ClientSummary(props: SummaryProps) {
  const { refId, role, client, usage, conversations, connected, notConnected = 0 } = props;
  const base = `/clients/${encodeURIComponent(refId)}`;

  return (
    <div className="flex flex-col gap-(--space-section)">
      {/* El orden cuenta una historia: **quién es** este cliente, **si
          atiende**, **cuánto gasta** y **con qué está conectado**. Los datos
          van primero porque son la identidad —y porque es el único bloque
          que se edita, así que enterrarlo al final obligaba a recorrer la
          pantalla entera para cambiar un nombre (owner, 2026-09-28). */}
      <ClientIdentity refId={refId} role={role} client={client} />

      <div className="grid grid-cols-1 gap-(--space-block) lg:grid-cols-2">
        <Credit refId={refId} role={role} quota={client.quota} usage={usage} />
        {conversations ? <Conversations base={base} block={conversations} /> : null}
      </div>

      <Connected refId={refId} block={connected} notConnected={notConnected} />
    </div>
  );
}

/**
 * Quién es este cliente, y si atiende.
 *
 * Antes eran dos bloques y decían lo mismo tres veces: la insignia de la
 * cabecera, la tarjeta de pasos —que ya nombra lo que falta— y un «Sin
 * atender · falta canal» debajo. Aquí queda **una** frase de estado, junto a
 * los datos que la explican, y los hechos sueltos (versión del agente,
 * canal) viven en la tarjeta de pasos, que es donde se resuelven.
 */
function ClientIdentity({ refId, role, client }: Pick<SummaryProps, "refId" | "role" | "client">) {
  const t = useT();
  const h = client.health;
  const base = `/clients/${encodeURIComponent(refId)}`;

  return (
    <Section
      title={t("sum.data")}
      description={t("sum.data.help")}
      actions={
        can(role, "agents:read") ? (
          <Button size="xs" variant="ghost" nativeButton={false} render={<Link href={`${base}/agent`} />}>
            {t("sum.seeAgent")}
          </Button>
        ) : undefined
      }
      className="min-w-0"
    >
      {can(role, "clients:write") ? (
        <SettingsForm refId={refId} name={client.name} timezone={client.timezone} />
      ) : (
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <div>
            <dt className="inline text-muted-foreground">{t("common.name")}: </dt>
            <dd className="inline">{client.name}</dd>
          </div>
          <div>
            <dt className="inline text-muted-foreground">{t("clients.timezone")}: </dt>
            <dd className="inline">{client.timezone}</dd>
          </div>
        </dl>
      )}

      {/* La línea de estado, debajo de los datos: una sola, y la única de
          toda la ficha que dice si el agente está atendiendo. */}
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-3 text-sm">
        <span className="inline-flex items-center gap-2">
          <StatusDot tone={h.ready ? "positive" : "warning"} />
          {h.ready ? t("sum.serving") : t("sum.notServing", { what: missingWhat(t, h) })}
        </span>
        {client.sector ? (
          <span className="text-muted-foreground">{t("sum.sector", { sector: client.sector })}</span>
        ) : null}
      </p>
    </Section>
  );
}

/** Lo que un bloque enseña cuando su lectura no llegó (R1.6). Se dice, se
 *  ofrece salida, y no se finge un cero. */
function Failed({ what }: { what: string }) {
  const t = useT();
  const router = useRouter();
  return (
    <Alert role="status" className="border-status-warning/40">
      <AlertDescription className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span>{t("sum.failed", { what })}</span>
        <Button size="xs" variant="outline" onClick={() => router.refresh()}>
          <RotateCw className="size-3" aria-hidden="true" />
          {t("sum.failed.retry")}
        </Button>
      </AlertDescription>
    </Alert>
  );
}

/** Lo que falta, en una palabra. La lista entera vive en la tarjeta de
 *  pasos; aquí solo se nombra para que el estado no sea un «no» seco. */
function missingWhat(t: ReturnType<typeof useT>, h: SummaryProps["client"]["health"]): string {
  if (!h.agent_version) return t("clients.setup.agent").toLowerCase();
  if (!h.whatsapp_connected) return t("clients.setup.channel").toLowerCase();
  return t("clients.setup.activation").toLowerCase();
}

// ── 2 · ¿cuánto consume? ────────────────────────────────────────────────

function Credit({
  refId,
  role,
  quota,
  usage,
}: Pick<SummaryProps, "refId" | "role" | "usage"> & { quota: SummaryProps["client"]["quota"] }) {
  const t = useT();
  const locale = useLocale();
  const empty = quota !== null && quota.remaining <= 0;

  return (
    <Section
      title={
        <span className="inline-flex items-center gap-1">
          {t("sum.credit")}
          <HelpHint label={t("sum.credit")}>{t("sum.credit.help")}</HelpHint>
        </span>
      }
      actions={
        can(role, "usage:read") ? (
          <Button
            size="xs"
            variant="ghost"
            nativeButton={false}
            render={<Link href={`/usage?client=${encodeURIComponent(refId)}`} />}
          >
            {t("sum.credit.detail")}
          </Button>
        ) : undefined
      }
      className="min-w-0"
    >
      {!usage.ok ? (
        <Failed what={t("sum.failed.credit")} />
      ) : quota === null ? (
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("sum.credit.none")}</p>
      ) : (
        <div className="flex flex-col gap-3">
          <Meter
            label={t("sum.credit")}
            labelHidden
            value={quota.remaining}
            max={quota.cap}
            tone={creditTone(quota)}
            valueLabel={t("sum.credit.value", {
              remaining: formatNumber(quota.remaining, locale),
              cap: formatNumber(quota.cap, locale),
            })}
            hint={t("sum.credit.spent", { spent: formatNumber(quota.cap - quota.remaining, locale) })}
          />
          {empty ? (
            <Alert role="status" className="border-status-warning/40">
              <AlertDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>{t("sum.credit.empty")}</span>
                {can(role, "usage:write") ? (
                  <Link
                    href={`/usage?client=${encodeURIComponent(refId)}`}
                    className="font-medium underline underline-offset-4"
                  >
                    {t("sum.credit.assign")}
                  </Link>
                ) : null}
              </AlertDescription>
            </Alert>
          ) : usage.data.units <= 0 ? (
            // R1.7: sin actividad no es cero. Un «0 gastados» junto a una
            // proyección de 0 se lee como que algo se ha roto.
            <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("sum.credit.noActivity")}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t("sum.credit.projection", {
                days: usage.data.basisDays,
                projected: formatNumber(Math.round(usage.data.projected), locale),
              })}
            </p>
          )}
        </div>
      )}
    </Section>
  );
}

/** La barra mide lo que QUEDA, así que su tono también. */
// ── 3 · ¿cómo va la conversación? ───────────────────────────────────────

function Conversations({
  base,
  block,
}: {
  base: string;
  block: NonNullable<SummaryProps["conversations"]>;
}) {
  const t = useT();
  const locale = useLocale();
  const none = block.ok && block.data.conversations === 0;

  return (
    <Section title={t("sum.conv")} description={t("sum.conv.window")} className="min-w-0">
      {!block.ok ? (
        <Failed what={t("sum.failed.conv")} />
      ) : none ? (
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("sum.conv.noActivity")}</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric
            label={t("sum.conv.total")}
            value={formatNumber(block.data.conversations, locale)}
            href={`${base}/conversations`}
          />
          <Metric
            label={t("sum.conv.escalated")}
            value={formatNumber(block.data.escalated, locale)}
            hint={t("sum.conv.escalated.share", {
              percent: Math.round((block.data.escalated / block.data.conversations) * 100),
            })}
            href={`${base}/conversations?escalated=true`}
          />
          <Metric
            label={t("sum.conv.failed")}
            value={formatNumber(block.data.failed_messages, locale)}
            href={`${base}/conversations?with_errors=true`}
          />
        </div>
      )}
    </Section>
  );
}

// ── 4 · ¿qué tiene conectado? ───────────────────────────────────────────

function Connected({
  refId,
  block,
  notConnected,
}: {
  refId: string;
  block: SummaryProps["connected"];
  notConnected: number;
}) {
  const t = useT();
  const base = `/clients/${encodeURIComponent(refId)}`;

  return (
    <Section
      title={t("sum.connected")}
      actions={
        <Button size="xs" variant="ghost" nativeButton={false} render={<Link href={`${base}/integrations`} />}>
          {t("sum.connected.all")}
        </Button>
      }
      className="min-w-0"
    >
      {!block.ok ? (
        <Failed what={t("sum.failed.connected")} />
      ) : block.data.length === 0 ? (
        // «Nada conectado» a secas se calla que hay conectores esperando, y
        // eso es lo único accionable que tiene este bloque.
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">
          {notConnected > 0 ? t("sum.connected.noneYet", { n: notConnected }) : t("sum.connected.none")}
        </p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {block.data.map((item) => {
            const broken = item.status !== "connected" && item.status !== "active";
            return (
              <li key={item.key} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                {broken ? (
                  <AlertTriangle className="size-4 shrink-0 text-status-warning" aria-hidden="true" />
                ) : null}
                <span className="font-medium">{item.name}</span>
                <StatusBadge tone={broken ? "danger" : "positive"}>
                  {t(`connectors.status.${item.status}` as "connectors.status.none")}
                </StatusBadge>
                {item.unlocks ? (
                  <span className="text-xs text-muted-foreground">
                    {item.unlocks === 1
                      ? t("sum.connected.unlocksOne")
                      : t("sum.connected.unlocks", { n: item.unlocks })}
                  </span>
                ) : null}
                {item.detail ? <span className="text-xs text-muted-foreground">{item.detail}</span> : null}
                {broken ? (
                  <Button
                    size="xs"
                    variant="outline"
                    className="ml-auto"
                    nativeButton={false}
                    render={<Link href={`${base}/integrations`} />}
                  >
                    {t("sum.connected.fix")}
                  </Button>
                ) : null}
              </li>
            );
          })}
          {notConnected > 0 ? (
            <li className="text-xs text-muted-foreground">{t("sum.connected.more", { n: notConnected })}</li>
          ) : null}
        </ul>
      )}
    </Section>
  );
}
