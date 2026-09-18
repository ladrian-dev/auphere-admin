/**
 * El plan, el cobro y el saldo — spec 010, Requisitos 9.1, 9.2, 9.6, 9.7 y 9.9.
 *
 * Lo que Cuenta no tenía y por eso ningún tope llevaba a ninguna parte: el
 * plan. «Cambia de plan, en Cuenta» mandaba a una pantalla donde no había plan.
 *
 * Cuatro decisiones, todas del requisito:
 *
 * * **proporción y fecha, nunca la cifra del pool** (R9.6). El tamaño del pool
 *   es provisional; imprimirlo convierte cada ajuste en un recorte o un regalo
 *   público. El saldo comprado sí va en unidades: es dinero que se pagó;
 * * **el aviso llega al 80 %** (R9.7), antes de agotarse, con la fecha de
 *   reinicio — un aviso al 100 % no es un aviso, es un parte;
 * * **un cobro degradado se dice antes de que se note en el trabajo** (R9.9).
 *   Hoy no se mencionaba en ninguna parte de la aplicación;
 * * **sin permiso no se ofrece la acción** (R9.2): se dice a quién pedírsela.
 *   Un botón que va a rebotar en un 403 es peor que un nombre.
 */
import { Button } from "@nexus/ui";

import { gateFor } from "../../gating";
import type { Membership } from "../bridge";
import { type AppKey, useAppT, useLang } from "../i18n";

/** El umbral del aviso. El que el producto ya usa en la consola. */
export const NEAR_LIMIT = 80;

/** Los estados de suscripción que degradan el servicio antes de notarse. */
const DEGRADED = new Set(["past_due", "unpaid", "incomplete"]);

export function Plan({
  membership,
  percent,
  resetsAt,
  permissions,
  onGo,
}: {
  membership: Membership | null;
  /** La proporción del pool usada. La cifra absoluta no se enseña (R9.6). */
  percent: number;
  resetsAt: string | null;
  permissions: readonly string[];
  onGo: (destination: { kind: "section"; section: string } | { kind: "console"; path: string }) => void;
}) {
  const t = useAppT();
  const lang = useLang();
  if (!membership) return null;

  const fecha = (iso: string) =>
    new Intl.DateTimeFormat(lang, { day: "numeric", month: "long" }).format(new Date(iso));

  const degraded = DEGRADED.has(membership.state);
  const cerca = percent >= NEAR_LIMIT;
  const lleno = membership.usage.teammates >= membership.tier.max_teammates;

  /** El tope que toca decir ahora, si hay alguno. Uno solo: el más grave. */
  const cap = degraded ? "cobro_fallido" : lleno ? "plan_lleno" : null;
  const gate = cap ? gateFor(cap, permissions) : null;

  return (
    <section className="flex min-w-0 flex-col gap-3" aria-label={t("plan.title")}>
      <h2 className="text-base font-semibold text-balance">{t("plan.title")}</h2>

      <p className="text-ui text-pretty">
        {t("plan.current", {
          name: membership.tier.display_name,
          teammates: membership.usage.teammates,
          max: membership.tier.max_teammates,
        })}
      </p>

      {/* R9.6: proporción y cuándo se reinicia. La cifra del pool, nunca. */}
      {resetsAt ? (
        <p className="text-ui text-pretty text-muted-foreground">
          {t("plan.pool", { percent: String(Math.round(percent)), date: fecha(resetsAt) })}
        </p>
      ) : null}

      {/* R9.7: antes de agotarse, no al agotarse. */}
      {cerca && resetsAt ? (
        <p className="max-w-prose rounded-md bg-muted p-3 text-ui text-pretty text-muted-foreground">
          {t("plan.near", { percent: String(Math.round(percent)), date: fecha(resetsAt) })}
        </p>
      ) : null}

      {/* R9.6: el saldo comprado sí va en unidades; es dinero que se pagó. */}
      {membership.purchased_expires_at ? (
        <p className="text-ui text-pretty text-muted-foreground">
          {t("plan.credit", { date: fecha(membership.purchased_expires_at) })}
        </p>
      ) : null}

      {/* R9.9: un cobro degradado se dice **antes** de que se note. */}
      {degraded ? (
        <p className="max-w-prose rounded-md bg-muted p-3 text-ui text-pretty">{t("plan.degraded")}</p>
      ) : null}

      {gate ? (
        gate.kind === "ask" ? (
          <p className="max-w-prose text-ui text-pretty text-muted-foreground">
            {t(`plan.ask.${gate.role}` as AppKey)}
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => onGo(gate.destination)}>
              {t(`plan.action.${cap}` as AppKey)}
            </Button>
          </div>
        )
      ) : (
        /* Sin tope, cambiar de plan sigue siendo posible — pero sólo para quien
           puede contratar: ofrecérselo a quien no puede es un 403 con retraso. */
        permissions.includes("billing:manage") ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => onGo({ kind: "console", path: "/billing" })}>
              {t("plan.change")}
            </Button>
          </div>
        ) : null
      )}
    </section>
  );
}
