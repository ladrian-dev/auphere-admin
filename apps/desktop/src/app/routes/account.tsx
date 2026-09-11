/**
 * Cuenta — spec 003, Requisitos 8 y 9.3.
 *
 * Cuatro cosas y ninguna que se administre desde aquí: cuánto va del mes y
 * quién lo gastó, el equipo con sus roles, la política de ejecución de esta
 * persona con el techo que la acota, y las dos puertas a la consola.
 *
 * El número **no se calcula aquí**. Es el mismo objeto que la consola pinta en
 * su medidor (R9.1), y el desglose viene de la misma tabla. Cuando el total y
 * el desglose no coinciden —porque el Companion de la consola gasta del mismo
 * sitio— la pantalla lo explica: dos cifras que no suman y nadie diciendo por
 * qué es la manera de que nadie vuelva a creerse ninguna.
 */
import { Button, Skeleton } from "@nexus/ui";
import * as React from "react";

import type { LocalExecPolicy } from "../bridge";
import { type AppKey, useAppT, useLang } from "../i18n";

export type UsageRow = {
  teammate_id: string;
  name: string;
  input_tokens: number;
  output_tokens: number;
  runs: number;
};

export type Budget = {
  used: number;
  cap: number;
  remaining: number;
  percent: number;
  exhausted: boolean;
  period: string;
  resets_at: string;
};

export type Usage = { budget: Budget; by_teammate: UsageRow[] };

export type TeamMember = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  status: string;
  is_you: boolean;
};

export type AccountProps = {
  status: "loading" | "ready" | "error";
  usage: Usage | null;
  /** `null` = no se pudo leer. El resto de Cuenta sigue en pie. */
  team: { members: TeamMember[] } | null;
  policy: LocalExecPolicy | null;
  onRetry: () => void;
  onOpenConsole: (path: string) => void;
};

const ROLE_KEY: Record<string, AppKey> = {
  owner: "account.role.owner",
  admin: "account.role.admin",
  builder: "account.role.builder",
  analyst: "account.role.analyst",
  billing: "account.role.billing",
};

export function Account({ status, usage, team, policy, onRetry, onOpenConsole }: AccountProps) {
  const t = useAppT();
  const lang = useLang();
  const nf = React.useMemo(() => new Intl.NumberFormat(lang), [lang]);

  if (status === "loading") {
    return (
      <div className="flex flex-col gap-3 p-6" role="status" aria-busy="true">
        <span className="sr-only">{t("account.loading")}</span>
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (status === "error" || usage === null) {
    return (
      <div className="flex flex-col items-start gap-3 p-6" role="status">
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("account.error")}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          {t("roster.retry")}
        </Button>
      </div>
    );
  }

  const { budget, by_teammate: rows } = usage;
  const attributed = rows.reduce((sum, r) => sum + r.input_tokens + r.output_tokens, 0);
  const elsewhere = Math.max(0, budget.used - attributed);

  return (
    <div className="flex min-w-0 flex-col gap-6 overflow-y-auto p-6">
      <section className="flex min-w-0 flex-col gap-2">
        <h2 className="text-base font-semibold text-balance">{t("account.usage.title")}</h2>
        {/* Un `<meter>` nativo no se puede vestir con los tokens sin pelearse
            con pseudo-elementos por motor, y aquí se veía como una barra blanca
            de otro sistema. La semántica es lo que importa —`role="meter"` con
            sus tres valores— y el color lo pone el diseño. */}
        <div
          role="meter"
          aria-label={t("account.usage.title")}
          aria-valuenow={budget.used}
          aria-valuemin={0}
          aria-valuemax={budget.cap}
          aria-valuetext={t("account.usage.valuetext", {
            used: nf.format(budget.used),
            cap: nf.format(budget.cap),
          })}
          className="h-2 w-full overflow-hidden rounded-full bg-muted"
        >
          {/* El único `style` de la pantalla, y es geometría en tiempo de
              ejecución —un porcentaje que sale del dato—, no tema: el color va
              en tokens. El mínimo del 2 % es para que un gasto pequeño se vea
              como una raya y no como nada. */}
          <div
            className={`h-full rounded-full ${budget.exhausted ? "bg-status-warning" : "bg-primary"}`}
            style={{ width: `${Math.min(100, Math.max(budget.used > 0 ? 2 : 0, budget.percent))}%` }}
          />
        </div>
        <p className="text-sm text-pretty">
          {t("account.usage.line", {
            used: nf.format(budget.used),
            cap: nf.format(budget.cap),
            resets: new Intl.DateTimeFormat(lang, { day: "numeric", month: "long" }).format(
              new Date(budget.resets_at),
            ),
          })}
        </p>

        {budget.exhausted ? (
          <p
            role="status"
            aria-label={t("account.usage.capped.label")}
            className="max-w-prose rounded-md bg-muted p-3 text-sm text-pretty text-muted-foreground"
          >
            {t("account.usage.capped")}
          </p>
        ) : null}

        {rows.length === 0 ? (
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">
            {t("account.usage.empty")}
          </p>
        ) : (
          <ul className="flex min-w-0 flex-col gap-1">
            {rows.map((row) => (
              <li key={row.teammate_id} className="flex min-w-0 items-baseline gap-2 text-sm">
                <span className="min-w-0 flex-1 truncate">{row.name}</span>
                <span className="text-muted-foreground tabular-nums">
                  {nf.format(row.input_tokens + row.output_tokens)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {t("account.usage.runs", { runs: row.runs })}
                </span>
              </li>
            ))}
          </ul>
        )}

        {elsewhere > 0 ? (
          <p className="max-w-prose text-xs text-pretty text-muted-foreground">
            {t("account.usage.elsewhere", { tokens: nf.format(elsewhere) })}
          </p>
        ) : null}
      </section>

      <section className="flex min-w-0 flex-col gap-2">
        <h2 className="text-base font-semibold text-balance">{t("account.team.title")}</h2>
        {team === null ? (
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">
            {t("account.team.unreadable")}
          </p>
        ) : (
          <>
            <ul className="flex min-w-0 flex-col gap-1">
              {team.members.map((member) => (
                <li key={member.id} className="flex min-w-0 items-baseline gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate">
                    {member.display_name || member.email}
                    {member.is_you ? ` · ${t("account.team.you")}` : ""}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {t(ROLE_KEY[member.role] ?? "account.role.unknown")}
                  </span>
                </li>
              ))}
            </ul>
            <p className="max-w-prose text-xs text-pretty text-muted-foreground">
              {t("account.team.readOnly")}
            </p>
          </>
        )}
      </section>

      {policy ? (
        <section className="flex min-w-0 flex-col gap-2">
          <h2 className="text-base font-semibold text-balance">{t("account.policy.title")}</h2>
          <p className="text-sm text-pretty">
            {t("account.policy.effective", { mode: t(`account.policy.mode.${policy.effective}`) })}
          </p>
          {policy.capped ? (
            <p
              role="status"
              aria-label={t("account.policy.title")}
              className="max-w-prose rounded-md bg-muted p-3 text-sm text-pretty text-muted-foreground"
            >
              {t("account.policy.capped", { mode: t(`account.policy.mode.${policy.ceiling}`) })}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => onOpenConsole("/")}>
            {t("account.openConsole")}
          </Button>
          {/* R8.3 y 002-R11.1: la aplicación **no añade** otra sesión ni otro
              cierre de sesión. Abre donde vive la suya y lo dice. */}
          <Button variant="outline" size="sm" onClick={() => onOpenConsole("/")}>
            {t("account.signOut")}
          </Button>
        </div>
        <p className="max-w-prose text-xs text-pretty text-muted-foreground">
          {t("account.signOut.hint")}
        </p>
      </section>
    </div>
  );
}
