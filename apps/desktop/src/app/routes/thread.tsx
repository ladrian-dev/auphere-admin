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
import { type Teammate, type TeammateChange, type ThreadRow, bridge } from "../bridge";
import { InlineNotice, useFeedback } from "../feedback/provider";
import { type AppKey, useAppT } from "../i18n";
import { ipcTransport } from "../transport-ipc";
import { ChangeNotes } from "./change-notes";
import { ThreadOpenError } from "./thread-open-error";
import { TurnStatus } from "./turn-status";

/*
 * Spec 010 R5.7 — `en_pausa_por_tope` **no** está aquí, y es a propósito.
 *
 * El compositor ya lo dice junto al cuadro que dejó de aceptar texto, con los
 * números y la salida; esta banda lo decía otra vez arriba, sin ninguna de las
 * dos cosas y con una salida distinta. Un hecho, un mecanismo.
 */
const BANNER_STATES: ThreadState[] = ["esperandote", "maquina_ausente", "parcial", "reconectando", "bloqueado"];

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

export function ThreadView({
  teammate,
  machinePresent,
  onRosterChanged,
  onOpenSettings,
  initialText,
  onDraftUsed,
}: {
  teammate: Teammate;
  machinePresent: boolean;
  onRosterChanged: () => void;
  onOpenSettings: () => void;
  /** Lo que se escribió en Hoy y viene a enviarse aquí (spec 013, R6). */
  initialText?: string;
  onDraftUsed?: () => void;
}) {
  const t = useAppT();
  const { notify, clear } = useFeedback();
  const controller = useCompanion(ipcTransport);
  const { state, status, errorDetail, partial, reconnecting, deciding, decisionFailure, openThread, setThreadId, send, decide } = controller;
  const [text, setText] = useState(initialText ?? "");

  /*
   * Lo escrito en Hoy se consume **una vez**: si se quedara puesto, volver al
   * hilo repetiría el texto que ya se envió. No hace falta excluir
   * dependencias — avisar vacía el borrador, así que `initialText` pasa a
   * indefinido y la guarda cierra el ciclo sola.
   */
  useEffect(() => {
    if (initialText) onDraftUsed?.();
  }, [initialText, onDraftUsed]);
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
    clear("thread.policy");
    const saved = await bridge.policySetPref({ executable, mode });
    if (saved.ok) {
      setCapped(saved.data.capped);
      return;
    }
    // R5.3: sin esto, elegir «siempre» y que no se guardara se veía igual que
    // haberlo guardado — hasta la siguiente vez que pidiera permiso.
    notify({
      severidad: "error",
      alcance: "elemento",
      urgencia: "diferible",
      slot: "thread.policy",
      clave: "feedback.policy.failed",
    });
  }, [state, notify, clear]);

  useEffect(() => {
    let alive = true;
    void bridge.rosterChanges({ id: teammate.id }).then((res) => {
      if (!alive) return;
      if (res.ok) {
        setChanges(res.data);
        return;
      }
      // No es grave —el hilo funciona igual— pero callarlo deja creyendo que
      // este teammate no ha cambiado, que es una afirmación, no una ausencia.
      notify({ severidad: "aviso", alcance: "vista", urgencia: "diferible", clave: "feedback.changes.failed" });
    });
    return () => {
      alive = false;
    };
  }, [teammate.id, notify]);

  /**
   * Spec 010 R4.2 — abrir el hilo puede fallar, y entonces se dice.
   *
   * Antes esto no tenía rama `else`: `useCompanion` arranca en `ready`, el
   * vacío se decide por «cero elementos», y el resultado era que un fallo de la
   * plataforma se pintaba como «tu hilo está vacío».
   */
  const [openFailed, setOpenFailed] = useState<{ detail?: string } | null>(null);

  /**
   * Las conversaciones de esta persona con este teammate — spec 013, R4.
   * Hasta aquí había una sola y eterna.
   */
  const [convs, setConvs] = useState<ThreadRow[]>([]);
  const [convId, setConvId] = useState<string | null>(null);

  const refreshConvs = useCallback(async () => {
    const r = await bridge.threadList({ teammate_id: teammate.id });
    if (r.ok) setConvs(r.data.filter((t) => t.archived_at === null));
  }, [teammate.id]);

  const openOnce = useCallback(
    (prefer?: string) => {
      setOpening(true);
      setOpenFailed(null);
      return bridge
        .threadOpen({ teammate_id: teammate.id, ...(prefer ? { prefer } : {}) })
        .then((res) => {
          setOpening(false);
          if (res.ok) {
            setThreadId(res.data.thread_id);
            setConvId(res.data.thread_id);
            void openThread(res.data.thread_id);
            void refreshConvs();
            return;
          }
          setOpenFailed({ ...(res.code ? { detail: res.code } : {}) });
        });
    },
    [teammate.id, openThread, setThreadId, refreshConvs],
  );

  /** Empezar una nueva, sin arrastrar lo anterior (R4.1). */
  const startNew = useCallback(async () => {
    const r = await bridge.threadCreate({ teammate_id: teammate.id });
    if (!r.ok) return;
    setThreadId(r.data.thread_id);
    setConvId(r.data.thread_id);
    await openThread(r.data.thread_id);
    await refreshConvs();
  }, [teammate.id, openThread, setThreadId, refreshConvs]);

  useEffect(() => {
    let alive = true;
    void refreshConvs();
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

  /**
   * Por qué ahora mismo no se puede editar ni reintentar (spec 013, R5.3-5.4).
   *
   * Lo que la persona tiene que hacer gana: con una confirmación esperando, lo
   * que toca es decidirla, no reescribir la pregunta. Y con un turno vivo,
   * rehacerlo desde atrás dejaría dos versiones mezcladas.
   */
  const bloqueo: "turno_en_marcha" | "decision_pendiente" | null =
    turn === "esperando_decision"
      ? "decision_pendiente"
      : turn !== null && !["terminado", "detenido", "fallido"].includes(turn)
        ? "turno_en_marcha"
        : null;
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
    clear("thread.send");
    void send(value, null, "build").then((res) => {
      setSending(false);
      if (res?.ok !== false) {
        setText("");
        void onRosterChanged();
        return;
      }
      // Conservar el texto (R4.5) sin decir por qué sigue ahí deja pensando
      // que la tecla no llegó a pulsarse.
      notify({
        severidad: "error",
        alcance: "elemento",
        urgencia: "diferible",
        slot: "thread.send",
        clave: "feedback.send.failed",
      });
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
        {/*
          Spec 013, R4 — las conversaciones con este teammate. Solo aparece
          cuando hay más de una: un selector con un elemento es un control que
          no decide nada.
        */}
        {convs.length > 1 ? (
          <label className="ml-auto flex min-w-0 items-center gap-2 text-xs">
            <span className="text-muted-foreground">{t("conv.pick")}</span>
            <select
              className="min-h-8 min-w-0 max-w-48 truncate rounded-md border border-border bg-background px-2 text-sm"
              value={convId ?? ""}
              onChange={(e) => void openOnce(e.target.value)}
            >
              {convs.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || t("conv.untitled")}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <button
          type="button"
          onClick={() => void startNew()}
          className={`${convs.length > 1 ? "" : "ml-auto "}min-h-8 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted`}
        >
          {t("conv.new")}
        </button>
        <button
          type="button"
          onClick={onOpenSettings}
          className="min-h-8 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted"
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
          onEditMessage={(t) => setText(t)}
          {...(bloqueo ? { actionsBlocked: bloqueo } : {})}
          onFetchExecOutput={async ({ executionId, clientRef }) => {
            // El cliente viene con el propio evento de despacho: una ejecución
            // siempre ocurre dentro del directorio declarado para uno.
            if (!clientRef) return { available: false };
            const r = await bridge.workstationExecOutput({
              client_ref: clientRef,
              execution_id: executionId,
            });
            return r.ok ? r.data : { available: false };
          }}
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
        <InlineNotice slot="thread.send" />
        <InlineNotice slot="thread.policy" />
        <Meters cost={state.cost} context={state.context} budget={state.budget} />
      </footer>
    </div>
  );
}
