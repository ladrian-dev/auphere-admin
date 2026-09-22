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
import { useState } from "react";

import type { Teammate, WorkstationView } from "../bridge";
import { WorkstationChip } from "../shell/workstation-chip";
import { useAppT } from "../i18n";

export type TodayProps = {
  /** El estado de la máquina, con su causa y sus acciones (R3.6). */
  workstation: WorkstationView | null;
  onOpenWorkstation: () => void;
  waiting: number;
  teammates: readonly Teammate[];
  status: "loading" | "ready" | "error" | "forbidden";
  onRetry: () => void;
  onOpenPending: () => void;
  onCreate: () => void;
  onOpenTeammate: (id: string) => void;
  /** Escribir lo primero y que eso abra la conversación (spec 013, R6). */
  onStart: (teammateId: string, text: string) => void;
};

export function Today({
  workstation,
  onOpenWorkstation,
  waiting,
  teammates,
  status,
  onRetry,
  onOpenPending,
  onCreate,
  onOpenTeammate,
  onStart,
}: TodayProps) {
  const t = useAppT();
  const [text, setText] = useState("");
  const [con, setCon] = useState<string | null>(null);
  const destinatario = con ?? teammates[0]?.id ?? null;

  /*
   * La máquina sólo ocupa sitio cuando hay algo que decir. Conectada y sin
   * directorios pendientes no se anuncia: la ausencia se diseña (§V), y una
   * tarjeta permanente diciendo «todo bien» es ruido que se aprende a ignorar.
   *
   * **Spec 012, R5.1 — y la carpeta también es algo que decir.** Antes sólo se
   * anunciaba una máquina que no estaba conectada, así que una recién
   * registrada y sin ningún directorio declarado no decía nada: quedaba
   * «conectada» y en silencio, sin poder tocar un fichero y sin decir por qué.
   *
   * Con el registro por sesión eso pasa de raro a ser **el estado normal del
   * primer arranque**, porque ya no hay una ceremonia de emparejar donde
   * enterarse. Y es la decisión que de verdad importa: qué carpeta toca un
   * teammate, no qué ordenador es éste.
   */
  const missingDirectories = workstation?.missing_directories ?? 0;
  const machineNeedsAttention =
    workstation !== null &&
    workstation.status !== "comprobando" &&
    (workstation.status !== "conectada" || missingDirectories > 0);

  const enviar = () => {
    const limpio = text.trim();
    // Un botón que no puede cumplir no se pulsa: sin texto o sin teammate no
    // hay conversación que empezar, y fingir que sí es la pantalla mintiendo.
    if (!limpio || !destinatario) return;
    onStart(destinatario, limpio);
    setText("");
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto p-6">
      {/*
        Spec 013, R6 — **lo primero es escribir.** Antes esta pantalla abría
        con el estado de la máquina y lo que esperaba decisión: todo cierto y
        todo administrativo. Lo que decide de qué clase de producto se trata es
        qué ocupa el centro al abrir.

        Sin teammates no se pinta: un sitio donde escribir que no lleva a
        ninguna parte es peor que no tenerlo (§V).
      */}
      {teammates.length > 0 ? (
        <section aria-labelledby="hoy-escribir" className="flex flex-col gap-2">
          <h2 id="hoy-escribir" className="sr-only">
            {t("today.start.send")}
          </h2>
          <div className="flex min-w-0 flex-col gap-2 rounded-md border border-border p-3">
            <textarea
              value={text}
              rows={3}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  enviar();
                }
              }}
              placeholder={t("today.start.placeholder")}
              className="min-w-0 resize-none rounded-sm bg-transparent text-ui outline-none"
            />
            <div className="flex flex-wrap items-center gap-2">
              {teammates.length > 1 ? (
                <label className="flex min-w-0 items-center gap-2 text-xs">
                  <span className="text-muted-foreground">{t("today.start.with")}</span>
                  <select
                    value={destinatario ?? ""}
                    onChange={(e) => setCon(e.target.value)}
                    className="min-h-8 min-w-0 rounded-md border border-border bg-background px-2 text-sm"
                  >
                    {teammates.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {t("today.start.with")} {teammates[0]?.name}
                </p>
              )}
              <Button size="sm" className="ml-auto" onClick={enviar}>
                {t("today.start.send")}
              </Button>
            </div>
          </div>
        </section>
      ) : null}

      {machineNeedsAttention ? (
        <section aria-labelledby="hoy-maquina" className="flex flex-col gap-2 rounded-md border border-border p-4">
          <h2 id="hoy-maquina" className="text-base font-semibold">
            {t("today.machine.title")}
          </h2>
          <WorkstationChip state={workstation} />
          {missingDirectories > 0 ? (
            <p className="text-ui text-pretty">
              {t("today.machine.needsDirectories", { count: String(missingDirectories) })}
            </p>
          ) : null}
          {workstation.actions.length > 0 ? (
            <div>
              <Button size="sm" onClick={onOpenWorkstation}>
                {/*
                  Con directorios pendientes, la acción que se ofrece es ésa y
                  no la primera de la lista: es lo que desbloquea el trabajo.
                */}
                {t(
                  `workstation.action.${
                    missingDirectories > 0 && workstation.actions.includes("directorios")
                      ? "directorios"
                      : workstation.actions[0]!
                  }`,
                )}
              </Button>
            </div>
          ) : null}
        </section>
      ) : null}
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
