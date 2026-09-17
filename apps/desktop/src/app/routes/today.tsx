/**
 * Hoy — spec 010, Requisito 7.9.
 *
 * La primera pantalla con la sesión iniciada **no está vacía**: ofrece lo
 * siguiente que tiene sentido hacer. Hasta ahora, al abrir la aplicación con el
 * equipo vacío se veían dos estados vacíos a la vez que se contradecían —«no
 * tienes teammates» a la izquierda y «elige un teammate» en el centro—, que es
 * lo que se vio al usar la app instalada.
 *
 * Esta vista es deliberadamente corta: lo que espera, el equipo y una acción.
 * Lo que la llena de verdad (la lista de puesta en marcha, el consumo, la
 * actividad) llega con las historias 4 y 5; su hueco está previsto, no
 * disimulado.
 */
import { Button } from "@nexus/ui";

import type { Teammate } from "../bridge";
import { useAppT } from "../i18n";

export type TodayProps = {
  waiting: number;
  teammates: readonly Teammate[];
  status: "loading" | "ready" | "error" | "forbidden";
  onRetry: () => void;
  onOpenPending: () => void;
  onCreate: () => void;
  onOpenTeammate: (id: string) => void;
};

export function Today({ waiting, teammates, status, onRetry, onOpenPending, onCreate, onOpenTeammate }: TodayProps) {
  const t = useAppT();

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto p-6">
      <section aria-labelledby="hoy-espera" className="flex flex-col gap-2">
        <h2 id="hoy-espera" className="text-base font-semibold">
          {t("today.waiting.title")}
        </h2>
        {waiting > 0 ? (
          <div className="flex items-center gap-3">
            <p className="text-ui text-pretty">{t("today.waiting.some", { count: String(waiting) })}</p>
            <Button size="sm" onClick={onOpenPending}>
              {t("today.waiting.open")}
            </Button>
          </div>
        ) : (
          <p className="text-ui text-pretty text-muted-foreground">{t("today.waiting.none")}</p>
        )}
      </section>

      <section aria-labelledby="hoy-equipo" className="flex flex-col gap-2">
        <h2 id="hoy-equipo" className="text-base font-semibold">
          {t("today.team.title")}
        </h2>

        {status === "loading" ? (
          <p className="text-ui text-muted-foreground" role="status">
            {t("roster.loading")}
          </p>
        ) : status === "error" ? (
          <div className="flex items-center gap-3">
            <p className="text-ui text-pretty">{t("roster.error")}</p>
            <Button size="sm" variant="outline" onClick={onRetry}>
              {t("roster.retry")}
            </Button>
          </div>
        ) : status === "forbidden" ? (
          <p className="max-w-prose text-ui text-pretty text-muted-foreground">{t("roster.forbidden")}</p>
        ) : teammates.length === 0 ? (
          <div className="flex max-w-prose flex-col items-start gap-3">
            <p className="text-ui text-pretty text-muted-foreground">{t("roster.empty.body")}</p>
            <Button size="sm" onClick={onCreate}>
              {t("roster.create")}
            </Button>
          </div>
        ) : (
          <ul className="flex flex-col gap-1">
            {teammates.map((teammate) => (
              <li key={teammate.id}>
                <button
                  type="button"
                  onClick={() => onOpenTeammate(teammate.id)}
                  className="flex min-h-8 w-full items-center gap-3 rounded-sm px-2 text-left text-ui transition-colors hover:bg-muted"
                >
                  <span className="min-w-0 flex-1 truncate">{teammate.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">{t(`state.${teammate.my_state}`)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
