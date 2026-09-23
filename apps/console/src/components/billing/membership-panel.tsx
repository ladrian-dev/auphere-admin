"use client";

/**
 * Spec 005 · la pantalla de planes.
 *
 * Tres decisiones que son constitución antes que diseño:
 *
 * **La ausencia se diseña (§V).** En el nivel gratuito no se pinta un botón
 * apagado de crear agente: no se pinta. Un control deshabilitado dice «esto
 * existe pero tú no» y deja a la persona averiguando por qué. Lo que sí se
 * dice es qué desbloquea un plan.
 *
 * **La cifra del pool no aparece (research D9).** Un nivel se describe por sus
 * topes —números estables, porque moverlos cambia el producto— y por un
 * múltiplo calculado. Las cifras son provisionales y van a ajustarse;
 * publicarlas convertiría cada ajuste de capacidad en un recorte o un regalo
 * visible, que es justo lo que la Spec A R7.3 prohíbe.
 *
 * **Los estados de impago dicen qué los arregla, y no culpan a nadie.** Una
 * tarjeta caducada es un problema de facturación, no una falta. Y lo primero
 * que dicen es lo que NO ha pasado: nada se ha perdido.
 */

import { useState } from "react";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  DescriptionList,
  StatusBadge,
  formatCurrency,
  formatDate,
} from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MembershipOut, SubscriptionState, TierOut } from "@/lib/backend/membership";

type Props = {
  membership: MembershipOut;
  onChoose?: (code: string) => Promise<void> | void;
  onFixCard?: () => Promise<void> | void;
  onCancel?: () => Promise<void> | void;
};

/** Estados que piden acción. `current` no pinta nada: no hay nada que arreglar. */
const TROUBLED: readonly SubscriptionState[] = ["payment_failed", "unpaid", "canceled"];

function TierCard({
  tier,
  current,
  onChoose,
  busy,
}: {
  tier: TierOut;
  current: boolean;
  onChoose?: (code: string) => Promise<void> | void;
  busy: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  return (
    <Card
      className={current ? "ring-2 ring-primary" : undefined}
      aria-current={current ? "true" : undefined}
    >
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span>{tier.display_name}</span>
          {current ? <StatusBadge tone="positive">{t("membership.currentBadge")}</StatusBadge> : null}
        </CardTitle>
        <CardDescription>
          {tier.monthly_price_cents === 0
            ? t("membership.free")
            : `${formatCurrency(tier.monthly_price_cents / 100, "USD", locale)} ${t("membership.perMonth")}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <DescriptionList
          layout="inline"
          dense
          items={[
            { key: "teammates", term: t("membership.teammates"), detail: <span className="tabular-nums">{tier.max_teammates}</span> },
            { key: "members", term: t("membership.members"), detail: <span className="tabular-nums">{tier.max_members}</span> },
            // El múltiplo, nunca la cifra. `null` en el gratuito: «0,2× el de
            // Pro» no le dice nada a quien todavía no tiene plan.
            ...(tier.consumption_multiple !== null
              ? [
                  {
                    key: "consumption",
                    term: t("membership.consumption"),
                    detail: tier.consumption_multiple === 1 ? t("membership.multiple.base") : t("membership.multiple", { n: tier.consumption_multiple }),
                  },
                ]
              : []),
          ]}
        />
        {!current && onChoose ? (
          <Button
            size="sm"
            disabled={busy}
            onClick={() => void onChoose(tier.code)}
          >
            {t("membership.choose", { tier: tier.display_name })}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function MembershipPanel({ membership, onChoose, onFixCard, onCancel }: Props) {
  const t = useT();
  const locale = useLocale();
  const [busy, setBusy] = useState(false);

  const { tier, state, usage, catalog } = membership;
  const troubled = TROUBLED.includes(state);

  async function choose(code: string) {
    if (!onChoose) return;
    setBusy(true);
    try {
      await onChoose(code);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {troubled ? (
        <Alert variant={state === "payment_failed" ? "default" : "destructive"}>
          <AlertTitle>{t(`membership.state.${state}.title` as never)}</AlertTitle>
          <AlertDescription className="flex flex-col gap-2">
            <p className="text-pretty">{t(`membership.state.${state}.body` as never)}</p>
            {membership.state_changed_at ? (
              <p className="text-muted-foreground text-xs">
                {t("membership.state.since", {
                  date: formatDate(membership.state_changed_at, locale),
                })}
              </p>
            ) : null}
            {state !== "canceled" && onFixCard ? (
              <Button size="sm" variant="outline" onClick={() => void onFixCard()}>
                {t("membership.state.fix")}
              </Button>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

      {membership.purchased_expires_at ? (
        <p className="text-muted-foreground text-sm text-pretty">
          {t("membership.credit.keeps", {
            date: formatDate(membership.purchased_expires_at, locale),
          })}
        </p>
      ) : null}

      {membership.pending_tier && membership.current_period_end ? (
        <Alert>
          <AlertDescription>
            {t("membership.pending", {
              tier:
                catalog.find((c) => c.code === membership.pending_tier)?.display_name ??
                membership.pending_tier,
              date: formatDate(membership.current_period_end, locale),
            })}
          </AlertDescription>
        </Alert>
      ) : null}

      {/* El nivel gratuito: se dice qué desbloquea un plan. Ningún control
          apagado esperando a que alguien lo pulse para explicarle que no. */}
      {tier.code === "free" ? (
        <section aria-labelledby="free-h" className="flex flex-col gap-2">
          <h2 id="free-h" className="text-lg font-semibold text-balance">
            {t("membership.free.title")}
          </h2>
          <p className="text-muted-foreground text-sm text-pretty">
            {t("membership.free.body")}
          </p>
        </section>
      ) : (
        <section aria-labelledby="current-h" className="flex flex-col gap-2">
          <h2 id="current-h" className="text-lg font-semibold">
            {t("membership.current")}
          </h2>
          <p className="text-sm text-pretty">
            {t("membership.usage", {
              teammates: usage.teammates,
              maxTeammates: tier.max_teammates,
              members: usage.members,
              maxMembers: tier.max_members,
            })}
          </p>
          {membership.current_period_end && state === "current" ? (
            <p className="text-muted-foreground text-sm">
              {t("membership.renews", {
                date: formatDate(membership.current_period_end, locale),
              })}
            </p>
          ) : null}
        </section>
      )}

      {/* Cancelar sólo se ofrece si hay algo que cancelar. En el gratuito y en
          una cuenta ya cancelada no se pinta apagado: no se pinta (§V). */}
      {tier.code !== "free" && state !== "canceled" && onCancel ? (
        <div>
          <Button variant="outline" size="sm" onClick={() => void onCancel()}>
            {t("membership.cancel")}
          </Button>
        </div>
      ) : null}

      <section aria-labelledby="catalog-h" className="flex flex-col gap-3">
        <h2 id="catalog-h" className="text-lg font-semibold">
          {t("membership.catalog")}
        </h2>
        {/* Side by side (owner, 2026-09-23): four plans in one row on a wide
            screen, two by two on a tablet, stacked on a phone. All alike: no
            «recommended» — the partner decides (owner, 2026-09-24). */}
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {catalog.map((entry) => (
            <TierCard
              key={entry.code}
              tier={entry}
              current={entry.code === tier.code}
              onChoose={entry.code === "free" ? undefined : choose}
              busy={busy}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
