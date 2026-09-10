/**
 * El hilo con un teammate (R3): corre en la plataforma; aquí se pinta con el
 * paquete compartido y se nombra su estado con `deriveThreadState`.
 */
import { Composer, type Decision, type IntakeSlot, Meters, Timeline, pendingAction, useCompanion } from "@nexus/companion-ui";
import { useEffect, useMemo, useState } from "react";

import { deriveThreadState, type ThreadState } from "../../app-state";
import { type Teammate, bridge } from "../bridge";
import { type AppKey, useAppT } from "../i18n";
import { ipcTransport } from "../transport-ipc";

const BANNER_STATES: ThreadState[] = ["esperandote", "en_pausa_por_tope", "maquina_ausente", "parcial", "reconectando"];

export function ThreadView({ teammate, machinePresent, onRosterChanged }: { teammate: Teammate; machinePresent: boolean; onRosterChanged: () => void }) {
  const t = useAppT();
  const controller = useCompanion(ipcTransport);
  const { state, status, errorDetail, partial, reconnecting, deciding, decisionFailure, openThread, setThreadId, send, decide } = controller;
  const [text, setText] = useState("");
  const [opening, setOpening] = useState(true);

  useEffect(() => {
    let alive = true;
    void bridge.threadOpen({ teammate_id: teammate.id }).then((res) => {
      if (!alive) return;
      setOpening(false);
      if (res.ok) {
        setThreadId(res.data.thread_id);
        void openThread(res.data.thread_id);
      }
    });
    return () => {
      alive = false;
    };
  }, [teammate.id, openThread, setThreadId]);

  const pending = pendingAction(state, Date.now());
  const busy = state.runStatus === "running";
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

  const onSend = () => {
    const value = text.trim();
    if (!value) return;
    setText("");
    void send(value, null, "build").then(onRosterChanged);
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
      </header>
      {BANNER_STATES.includes(threadState) ? (
        <p className="border-b border-border bg-muted px-4 py-2 text-sm text-pretty text-muted-foreground" role="status" data-thread-state={threadState}>
          {t(`thread.state.${threadState}` as AppKey, { name: teammate.name })}
        </p>
      ) : null}
      {/* El vacío es de la app y no del cajón de la consola: aquel habla de
          modos («en modo Consultar solo leo») que aquí no existen — el modo lo
          fija el teammate. Dos vacíos serían dos pantallas, y una mentiría. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3" data-thread-state={threadState}>
        {threadState === "vacio" ? (
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
        />
        )}
      </div>
      <footer className="border-t border-border px-4 py-3">
        <Composer
          value={text}
          mode="build"
          busy={busy}
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
