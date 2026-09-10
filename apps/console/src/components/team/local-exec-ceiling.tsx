"use client";

/**
 * El techo de ejecución local del partner — spec 003, Requisito 10.1.
 *
 * Está en Equipo y no en el puesto de trabajo porque no es configuración de una
 * máquina: es **hasta dónde puede llegar cada persona** con la suya. Tres
 * valores y ninguna casilla:
 *
 * * *Cada persona decide* — el techo no restringe (es el estado de partida).
 * * *Preguntar siempre* — nadie puede saltarse la tarjeta, ni queriendo.
 * * *Nadie ejecuta* — se apaga la ejecución local para todo el equipo.
 *
 * Lo que **no** hace, y se dice en pantalla porque si no se supone: bajar el
 * techo no revoca los permisos de argumentos ya concedidos. Esos se revocan
 * uno a uno en el puesto de trabajo del cliente, donde consta quién los dio.
 */
import * as React from "react";

import { Button, Card, CardContent, CardHeader, CardTitle } from "@nexus/ui";

import { setLocalExecCeilingAction } from "@/app/(console)/team/actions";
import { useT } from "@/i18n/client";
import type { ExecMode } from "@/lib/backend";

const MODES: readonly ExecMode[] = ["always", "ask", "never"] as const;

export function LocalExecCeiling({ ceiling, manage }: { ceiling: ExecMode; manage: boolean }) {
  const t = useT();
  const [current, setCurrent] = React.useState<ExecMode>(ceiling);
  const [pending, startTransition] = React.useTransition();
  const [failed, setFailed] = React.useState(false);

  const choose = (mode: ExecMode) => {
    if (mode === current) return;
    const previous = current;
    setCurrent(mode);
    setFailed(false);
    startTransition(async () => {
      const result = await setLocalExecCeilingAction({ ceiling: mode });
      if (!result.ok) {
        // Se vuelve a lo que había: dejar el botón marcado sería decir que se
        // guardó algo que no se guardó.
        setCurrent(previous);
        setFailed(true);
      }
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("team.localExec.title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-3">
        <p className="text-sm text-pretty text-muted-foreground">{t("team.localExec.description")}</p>
        <div role="group" aria-label={t("team.localExec.title")} className="flex min-w-0 flex-wrap gap-2">
          {MODES.map((mode) => (
            <Button
              key={mode}
              type="button"
              size="sm"
              variant={current === mode ? "default" : "outline"}
              aria-pressed={current === mode}
              disabled={!manage || pending}
              onClick={() => choose(mode)}
            >
              {t(`team.localExec.${mode}`)}
            </Button>
          ))}
        </div>
        <p className="text-xs text-pretty text-muted-foreground">{t("team.localExec.note")}</p>
        {failed ? (
          <p className="text-sm text-pretty text-status-warning" role="status">
            {t("team.localExec.failed")}
          </p>
        ) : null}
        {!manage ? (
          <p className="text-xs text-pretty text-muted-foreground" role="note">
            {t("team.localExec.readOnly")}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
