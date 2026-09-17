/**
 * El hilo con un teammate (R3): corre en la plataforma; aquí se pinta con el
 * paquete compartido y se nombra su estado con `deriveThreadState`.
 */
import {
  Composer,
  type Decision,
  type ExecMode,
  type IntakeSlot,
  Meters,
  Timeline,
  pendingAction,
  useCompanion,
} from "@nexus/companion-ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import { deriveThreadState, type ThreadState } from "../../app-state";
import { deriveTurnState, offersStop, turnFactsOf } from "../../turn-state";
import { type Teammate, type TeammateChange, bridge } from "../bridge";
import { type AppKey, useAppT } from "../i18n";
import { ipcTransport } from "../transport-ipc";
import { ChangeNotes } from "./change-notes";
import { ThreadOpenError } from "./thread-open-error";
import { TurnStatus } from "./turn-status";

const BANNER_STATES: ThreadState[] = ["esperandote", "en_pausa_por_tope", "maquina_ausente", "parcial", "reconectando"];

/** El ejecutable de la tarjeta que está esperando, si es de máquina. */
function pendingExecutable(state: { items: Array<Record<string, unknown>> }): string | null {
  for (const item of [...state.items].reverse()) {
    if (item.kind !== "action" || item.actionKind !== "local_exec") continue;
    const preview = item.preview as Record<string, unknown> | undefined;
    const executable = preview?.executable;
    return typeof executable === "string" ? executable : null;
  }
  return null;
}

export function ThreadView({ teammate, machinePresent, onRosterChanged, onOpenSettings }: { teammate: Teammate; machinePresent: boolean; onRosterChanged: () => void; onOpenSettings: () => void }) {
  const t = useAppT();
  const controller = useCompanion(ipcTransport);
  const { state, status, errorDetail, partial, reconnecting, deciding, decisionFailure, openThread, setThreadId, send, decide } = controller;
  const [text, setText] = useState("");
  // El hueco que no se veía (R4.3): el mensaje salió de aquí y el servidor
  // todavía no abrió el turno, así que `runStatus` sigue en reposo.
  const [sending, setSending] = useState(false);
  const [opening, setOpening] = useState(true);
  // Lo que cambió de este teammate mientras esta persona no miraba (R2.4). Se
  // lee al abrir: no hay evento, y por eso no puede perderse por estar cerrada
  // la aplicación.
  const [changes, setChanges] = useState<TeammateChange[]>([]);
  // El techo del partner, para poder decir la verdad en la tarjeta (R10.4).
  const [capped, setCapped] = useState(false);

  useEffect(() => {
    void bridge.policyPrefs().then((res) => {
      if (res.ok) setCapped(res.data.capped);
    });
  }, []);

  const onExecPolicy = useCallback(async (mode: Exclude<ExecMode, "ask">) => {
    // Se guarda **por ejecutable**, no global: decir «siempre» a `make test` no
    // es decírselo a todo lo que un teammate quiera correr mañana.
    const executable = pendingExecutable(state);
    const saved = await bridge.policySetPref({ executable, mode });
    if (saved.ok) setCapped(saved.data.capped);
  }, [state]);

  useEffect(() => {
    let alive = true;
    void bridge.rosterChanges({ id: teammate.id }).then((res) => {
      if (alive && res.ok) setChanges(res.data);
    });
    return () => {
      alive = false;
    };
  }, [teammate.id]);

  /**
   * Spec 010 R4.2 — abrir el hilo puede fallar, y entonces se dice.
   *
   * Antes esto no tenía rama `else`: `useCompanion` arranca en `ready`, el
   * vacío se decide por «cero elementos», y el resultado era que un fallo de la
   * plataforma se pintaba como «tu hilo está vacío».
   */
  const [openFailed, setOpenFailed] = useState<{ detail?: string } | null>(null);

  const openOnce = useCallback(() => {
    setOpening(true);
    setOpenFailed(null);
    return bridge.threadOpen({ teammate_id: teammate.id }).then((res) => {
      setOpening(false);
      if (res.ok) {
        setThreadId(res.data.thread_id);
        void openThread(res.data.thread_id);
        return;
      }
      setOpenFailed({ ...(res.code ? { detail: res.code } : {}) });
    });
  }, [teammate.id, openThread, setThreadId]);

  useEffect(() => {
    let alive = true;
    void openOnce().then(() => {
      if (!alive) return;
    });
    return () => {
      alive = false;
    };
  }, [openOnce]);

  const pending = pendingAction(state, Date.now());
  /*
   * Los ocho estados del turno (R4.3). Hasta aquí la pantalla distinguía dos:
   * el botón de enviar cambiaba a un cuadrado. Razonar, llamar a una
   * herramienta y esperar la primera palabra del servidor se veían igual.
   */
  const turn = useMemo(() => deriveTurnState(turnFactsOf(state, sending)), [state, sending]);
  // `busy` cierra el envío; detener solo se ofrece cuando hay turno que parar.
  const busy = sending || state.runStatus === "running";
  const threadState = useMemo(
    () =>
      deriveThreadState({
        status: opening ? "loading" : status,
        runStatus: state.runStatus,
        reconnecting,
        partial,
        itemCount: state.items.length,
        taskState: null,
        budgetPaused: state.paused !== null,
        machineNeeded: teammate.local_exec,
        machinePresent,
      }),
    [opening, status, state.runStatus, state.items.length, state.paused, reconnecting, partial, teammate.local_exec, machinePresent],
  );

  /**
   * Spec 010 R4.5 — lo escrito **no se pierde** si el envío falla.
   *
   * Antes el cuadro se vaciaba antes de saber el resultado: con la red caída o
   * la sesión recién perdida, el mensaje desaparecía y había que volver a
   * escribirlo de memoria. Ahora se vacía **cuando sale**, y si no sale se
   * queda donde estaba, listo para reintentar.
   */
  const onSend = () => {
    const value = text.trim();
    if (!value) return;
    setSending(true);
    void send(value, null, "build").then((res) => {
      setSending(false);
      if (res?.ok !== false) setText("");
      void onRosterChanged();
    });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-3 border-b border-border px-4 py-3">
        <span aria-hidden="true" className="flex size-8 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary">
          {teammate.name.slice(0, 1)}
        </span>
        <div className="flex min-w-0 flex-col">
          <h2 className="truncate text-sm font-semibold" title={teammate.name}>
            {teammate.name}
          </h2>
          <p className="truncate text-xs text-muted-foreground">{teammate.job}</p>
        </div>
        <button
          type="button"
          onClick={onOpenSettings}
          className="ml-auto min-h-8 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted"
        >
          {t("settings.open")}
        </button>
      </header>
      <ChangeNotes changes={changes} />
      {BANNER_STATES.includes(threadState) ? (
        <p className="border-b border-border bg-muted px-4 py-2 text-sm text-pretty text-muted-foreground" role="status" data-thread-state={threadState}>
          {t(`thread.state.${threadState}` as AppKey, { name: teammate.name })}
        </p>
      ) : null}
      {/* El vacío es de la app y no del cajón de la consola: aquel habla de
          modos («en modo Consultar solo leo») que aquí no existen — el modo lo
          fija el teammate. Dos vacíos serían dos pantallas, y una mentiría.
          Se mira **si el hilo está vacío**, no si el estado derivado se llama
          `vacio`: con la máquina ausente o reconectando el estado es ese otro,
          y hasta que se miró con display el hilo recién abierto enseñaba el
          vacío del cajón —con su «pregunta lo que quieras sobre tus clientes»—
          debajo de la banda de la máquina. Se exige `ready` y no «distinto de
          cargando» porque un hilo que falló al abrirse también tiene cero
          elementos, y decirle «está vacío» sería tapar el error. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3" data-thread-state={openFailed ? "error" : threadState}>
        {openFailed ? (
          <ThreadOpenError name={teammate.name} onRetry={() => void openOnce()} {...openFailed} />
        ) : !opening && status === "ready" && state.items.length === 0 ? (
          <p className="mx-auto max-w-prose py-12 text-center text-pretty text-muted-foreground">
            {t("thread.state.vacio", { name: teammate.name })}
          </p>
        ) : (
        <Timeline
          state={state}
          status={opening ? "loading" : status}
          errorDetail={errorDetail}
          partial={partial}
          currentUserId={null}
          deciding={deciding}
          decisionFailure={decisionFailure}
          suggestions={[]}
          onRetry={() => {
            void bridge.threadOpen({ teammate_id: teammate.id }).then((r) => {
              if (r.ok) void openThread(r.data.thread_id);
            });
          }}
          onSuggestion={(s) => setText(s)}
          onAnswerSlot={(slot: IntakeSlot) => setText(slot.label || slot.key)}
          onDecide={(actionId: string, decision: Decision, note?: string) => void decide(actionId, decision, note).then(onRosterChanged)}
          onExecPolicy={(mode) => void onExecPolicy(mode)}
          execCapped={capped}
        />
        )}
      </div>
      <TurnStatus state={turn} tool={turnFactsOf(state, sending).tool} />
      <footer className="border-t border-border px-4 py-3">
        <Composer
          value={text}
          mode="build"
          busy={busy}
          stoppable={offersStop(turn)}
          blocked={!!pending}
          paused={state.paused}
          exhausted={state.budget?.exhausted ?? false}
          onChange={setText}
          onSend={onSend}
          onStop={() => void controller.stop()}
        />
        <Meters cost={state.cost} context={state.context} budget={state.budget} />
      </footer>
    </div>
  );
}
