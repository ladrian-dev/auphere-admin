"use client";

import { CalendarCheck, LoaderCircle, MoreHorizontal } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Skeleton,
  StatusBadge,
  buttonVariants,
} from "@nexus/ui";

import { agendaToolsAction, agentAgendaAction, setAgentAgendaAction } from "@/app/(console)/clients/[ref]/agents/agenda-actions";
import { setConnectorToolAction } from "@/app/(console)/clients/[ref]/agents/connector-actions";
import { ReservasFields } from "@/components/clients/access/reservas-fields";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ConnectorTools } from "@/lib/backend/agent-connectors-types";
import type { AgendaBody, AgentAgenda, ReservasChoice } from "@/lib/backend/agenda-types";
import type { CapabilityUpdated } from "@/lib/backend/capabilities";
import type { CapacityKind, ReservasMode } from "@/lib/backend/client-access";

import { completedByClient, notReady, notReadyReasons, proposalFailed, proposalRunning, reasonKey, reasonLink, rowStatus } from "./agenda-model";
import { POLL_FIRST_MS, nextDelay, sleep, type Result } from "./builder-model";
import { ConnectorToolsDialog } from "./connector-tools-dialog";

type Ids = { ref: string; agent: string };
export type AgendaActions = {
  load: (body: Ids) => Promise<Result<AgentAgenda>>;
  set: (body: Ids & AgendaBody) => Promise<Result<AgentAgenda>>;
  tools: (body: Ids & { lang: "es" | "en" }) => Promise<Result<ConnectorTools>>;
  setTool: (body: Ids & { key: string; enabled: boolean }) => Promise<Result<CapabilityUpdated>>;
};

const SERVER_ACTIONS: AgendaActions = {
  load: (body) => agentAgendaAction(body),
  set: (body) => setAgentAgendaAction(body),
  tools: (body) => agendaToolsAction(body),
  setTool: (body) => setConnectorToolAction(body),
};

/** Los códigos que la API da al cambiar la agenda (`console-api.md` §4), dichos con palabras. */
const ERRORS: ReadonlySet<string> = new Set([
  "reservas_mode_required",
  "reservas_kind_required",
  "reservas_kind_forbidden",
  "archived",
  "no_partner",
  "spec_invalid",
]);

/**
 * «Agenda (Reservas)», la primera fila de Conectores de un agente (spec 057,
 * historia 3; requisitos 2.1–2.5, 3.5 y 4.4). No es un conector: no se conecta ni
 * tiene permiso, y su ancla es `#agenda` («Gestionar citas» lleva aquí).
 *
 * - **Activar** pone las 9 herramientas de Reservas en el borrador, de una vez, y
 *   rige al publicar. Con Reservas apagado, antes pide confirmación: se enciende
 *   para todo el cliente, y con qué modo (el del sector, ya elegido).
 * - **Desactivar** las quita del borrador. Reservas sigue encendido y las citas
 *   ya dadas, donde estaban.
 * - **Qué puede hacer**, en su menú: las 9, de una en una, con el diálogo de los
 *   conectores. Solo con la agenda activa: se activa entera.
 * - La **propuesta** de su texto de citas: mientras se escribe se dice (y se
 *   vuelve a leer hasta que llega), abierta lleva a ella, y si no se pudo escribir
 *   o no queda partida, se dice. Con la agenda activa en un agente estructurado y
 *   nada pendiente, «Pedir la propuesta» (el caso de Spa Jemma: la agenda llegó y
 *   el texto seguía mandando la cita al equipo).
 *
 * Sus cinco estados: cargando (una fila de esqueleto con su forma), vacío
 * (Reservas no se ofrece: no hay fila, §V), error (con «Reintentar»), parcial
 * (Reservas encendido y sin terminar: qué falta y dónde se completa) e ideal.
 * `agenda` en `undefined` se lee al montar; en `null`, no se pudo leer.
 */
export function AgendaRow({
  refId,
  agentId,
  canWrite,
  agenda: given,
  clientName = null,
  onAgenda,
  onChanged,
  onProposal,
  actions: over,
  wait = sleep,
}: {
  refId: string;
  agentId: string;
  canWrite: boolean;
  agenda?: AgentAgenda | null;
  clientName?: string | null;
  /** Cada lectura o escritura nueva: la ficha del agente dice lo mismo que la fila. */
  onAgenda?: (agenda: AgentAgenda) => void;
  /** El borrador cambió (las herramientas o la propuesta llegó): la pantalla lo vuelve a leer. */
  onChanged?: () => void;
  /** «Ver la propuesta»: la lista de propuestas del agente. */
  onProposal?: () => void;
  actions?: Partial<AgendaActions>;
  wait?: (ms: number) => Promise<void>;
}) {
  const t = useT();
  const actions = React.useMemo(() => ({ ...SERVER_ACTIONS, ...over }), [over]);
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [data, setData] = React.useState<AgentAgenda | null | undefined>(given);
  const [seen, setSeen] = React.useState(given);
  if (given !== seen) {
    setSeen(given);
    if (given !== undefined) setData(given);
  }
  const [loading, setLoading] = React.useState(given === undefined);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [reason, setReason] = React.useState<AgentAgenda["proposal_reason"]>(null);
  const [confirming, setConfirming] = React.useState(false);
  const [confirmError, setConfirmError] = React.useState<string | null>(null);
  const [mode, setMode] = React.useState<ReservasMode | null>(null);
  const [kind, setKind] = React.useState<CapacityKind | null>(null);
  const [toolsOpen, setToolsOpen] = React.useState(false);

  // Lo último que se pasó, para que la espera de la propuesta no se reinicie con cada pintura.
  const latest = React.useRef({ actions, ids, onAgenda, onChanged, wait });
  React.useEffect(() => {
    latest.current = { actions, ids, onAgenda, onChanged, wait };
  });
  const report = React.useCallback((next: AgentAgenda) => {
    setData(next);
    latest.current.onAgenda?.(next);
  }, []);

  const load = React.useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      const res = await latest.current.actions.load(latest.current.ids);
      setLoading(false);
      if (res.ok) report(res.data);
      else if (!silent) setData(null);
    },
    [report],
  );

  // Sin datos del servidor: se lee al montar.
  const asked = React.useRef(given !== undefined);
  React.useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    void load();
  }, [load]);

  // La propuesta se escribe aparte (un trabajo del constructor): se vuelve a leer,
  // con la espera creciente de siempre, hasta que termina. Entonces la pantalla
  // vuelve a leer el borrador y sus propuestas.
  const running = proposalRunning(data);
  const jobId = data?.job?.id ?? null;
  React.useEffect(() => {
    if (!running) return;
    let cancelled = false;
    void (async () => {
      let delay = POLL_FIRST_MS;
      for (;;) {
        await latest.current.wait(delay);
        if (cancelled) return;
        const res = await latest.current.actions.load(latest.current.ids);
        if (cancelled) return;
        if (res.ok) {
          report(res.data);
          if (!proposalRunning(res.data)) {
            latest.current.onChanged?.();
            return;
          }
        }
        delay = nextDelay(delay, false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [running, jobId, report]);

  function errorText(res: { status: number; code?: string | null; info?: Record<string, unknown> }): string {
    if (res.status === 401 || res.status === 403) return t("common.forbidden");
    if (res.code === "too_many_tools") {
      const max = typeof res.info?.max === "number" ? res.info.max : (data?.max_tools ?? 60);
      return t("agenda.error.too_many_tools", { max });
    }
    if (res.code && ERRORS.has(res.code)) return t(`agenda.error.${res.code}` as MessageKey);
    return t("agenda.error.generic");
  }

  /** Una escritura: `true` si salió; si no, lo que hay que decir. */
  async function change(enabled: boolean, reservas?: ReservasChoice, quiet = false): Promise<true | string> {
    setBusy(true);
    setError(null);
    const res = await actions.set({ ...ids, enabled, ...(reservas ? { reservas } : {}) });
    setBusy(false);
    if (!res.ok) return errorText(res);
    report(res.data);
    setReason(res.data.proposal_reason ?? null);
    if (!quiet) toast.success(enabled ? t("agenda.row.saved.on") : t("agenda.row.saved.off"));
    onChanged?.();
    return true;
  }

  async function toggle() {
    if (!data || busy) return;
    if (!data.draft.on && !data.module.on) {
      // 2.3: encender Reservas es para todo el cliente. Se pregunta, con el modo de su sector.
      setMode(data.suggested.mode);
      setKind(data.suggested.mode === "capacity" ? data.suggested.capacity_kind : null);
      setConfirmError(null);
      setConfirming(true);
      return;
    }
    const done = await change(!data.draft.on);
    if (done !== true) setError(done);
  }

  async function confirm() {
    if (mode === null || (mode === "capacity" && kind === null)) return;
    const done = await change(true, { mode, capacity_kind: mode === "capacity" ? kind : null });
    if (done === true) setConfirming(false);
    else setConfirmError(done);
  }

  /**
   * 3.1 y 3.5: pedir la propuesta, o volver a pedirla si no se pudo escribir. Es
   * el mismo `PUT` con el mismo estado: la API la encola si no hay trabajo en
   * curso ni propuesta abierta. No cambia la agenda, así que no lo celebra.
   */
  async function retryProposal() {
    if (!data || busy) return;
    const done = await change(data.draft.on, undefined, true);
    if (done !== true) setError(done);
  }

  if (data === undefined || (loading && data === null)) {
    // Con la forma de la fila: el icono, el nombre, su nota y el botón.
    return (
      <li className="flex min-w-0 items-center gap-3 px-4 py-4 sm:px-5" data-slot="agenda-row" data-state="loading" aria-busy="true">
        <Skeleton className="size-10 shrink-0" />
        <div className="grid min-w-0 flex-1 gap-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-3/4" />
        </div>
        <Skeleton className="h-8 w-24 shrink-0" />
        <span role="status" className="sr-only">
          {t("agenda.row.loading")}
        </span>
      </li>
    );
  }

  if (data === null) {
    return (
      <li className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-4 sm:px-5" data-slot="agenda-row" data-state="error">
        <AgendaIcon />
        <div className="grid min-w-0 flex-1 basis-56 gap-1">
          <h3 className="min-w-0 font-medium break-words">{t("agenda.row.name")}</h3>
          <p className="text-sm text-pretty text-muted-foreground">{t("agenda.row.error")}</p>
        </div>
        <Button size="sm" variant="outline" className="shrink-0" onClick={() => void load()}>
          {t("agenda.row.retry")}
        </Button>
      </li>
    );
  }

  // §V: lo que no se ofrece no se enseña, ni apagado.
  if (!data.offered) return null;

  const status = rowStatus(data);
  const writable = canWrite && data.can_write;
  const partial = notReady(data);
  const note = [
    t("agenda.switch.hint"),
    !data.module.on ? t("agenda.row.moduleOff") : null,
    status === "prepared" ? t("agenda.row.prepared") : status === "leaving" ? t("agenda.row.leaving") : status === "off" ? t("agenda.row.off") : null,
    data.draft.on ? t("agenda.row.tools", { n: data.draft.tools_on }) : null,
  ].filter(Boolean);
  const confirmable = mode !== null && (mode !== "capacity" || kind !== null);
  const line = textLine(data, reason, writable);

  return (
    <li
      id="agenda"
      // Destino de «Gestionar citas» y «Pedir la propuesta»: recibe el foco al llegar.
      tabIndex={-1}
      className="grid min-w-0 scroll-mt-24 gap-3 px-4 py-4 outline-none sm:px-5"
      data-slot="agenda-row"
      data-state={partial ? "partial" : "ideal"}
      data-status={status}
      aria-busy={busy || undefined}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-3">
        <AgendaIcon />
        <div className="grid min-w-0 flex-1 basis-56 gap-1">
          <h3 className="min-w-0 font-medium break-words">{t("agenda.row.name")}</h3>
          <p className="text-sm text-pretty text-muted-foreground">{note.join(" · ")}</p>
        </div>
        {/* `max-w-full`: en un móvil, envuelve en vez de salirse. */}
        <div className="flex max-w-full shrink-0 flex-wrap items-center gap-2">
          {status === "on" ? (
            <StatusBadge tone="positive" data-slot="agenda-state">
              {t("agenda.row.on")}
            </StatusBadge>
          ) : null}
          {writable ? (
            <Button
              size="sm"
              variant="outline"
              loading={busy && !confirming}
              disabled={busy}
              onClick={() => void toggle()}
              aria-label={data.draft.on ? t("agenda.row.deactivate.named") : t("agenda.row.activate.named")}
              aria-haspopup={!data.draft.on && !data.module.on ? "dialog" : undefined}
            >
              {data.draft.on ? t("agenda.row.deactivate") : t("agenda.row.activate")}
            </Button>
          ) : data.draft.on ? (
            <Button size="sm" variant="outline" onClick={() => setToolsOpen(true)} aria-haspopup="dialog">
              {t("agenda.row.whatItDoes")}
            </Button>
          ) : null}
          {writable && data.draft.on ? (
            <DropdownMenu>
              <DropdownMenuTrigger
                aria-label={t("agenda.row.more")}
                disabled={busy}
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
                data-slot="agenda-more"
              >
                <MoreHorizontal aria-hidden="true" className="size-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem onClick={() => setToolsOpen(true)}>{t("agenda.row.whatItDoes")}</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>

      {partial ? <AgendaNotReady refId={refId} missing={data.missing} /> : null}

      {/* Siempre montada y nunca oculta (una región oculta no se anuncia): un lector de
          pantalla oye cada cambio de la propuesta. Vacía, devuelve el hueco de la rejilla. */}
      <div role="status" className="min-w-0 empty:-mt-3" data-slot="agenda-text" data-state={line ?? "none"}>
        <TextLineContent
          line={line}
          busy={busy}
          canWrite={writable}
          onProposal={onProposal}
          onRetry={() => void retryProposal()}
          onAsk={() => void retryProposal()}
        />
      </div>

      {error ? (
        <p role="alert" className="text-sm text-pretty text-destructive">
          {error}
        </p>
      ) : null}

      <ConfirmDialog
        open={confirming}
        onOpenChange={(open) => {
          if (!open && !busy) setConfirming(false);
        }}
        title={clientName ? t("agenda.confirm.title.named", { client: clientName }) : t("agenda.confirm.title")}
        description={t("agenda.confirm.body")}
        confirmLabel={t("agenda.confirm.action")}
        cancelLabel={t("common.cancel")}
        confirmDisabled={!confirmable}
        onConfirm={confirm}
        error={confirmError ?? undefined}
      >
        <ReservasFields
          mode={mode}
          kind={kind}
          disabled={busy}
          onMode={(m) => {
            setMode(m);
            if (m === "capacity" && kind === null) setKind(data.suggested.capacity_kind);
            setConfirmError(null);
          }}
          onKind={(k) => {
            setKind(k);
            setConfirmError(null);
          }}
        />
      </ConfirmDialog>

      {toolsOpen ? (
        <ConnectorToolsDialog
          connector={{ name: t("agenda.row.name") }}
          canWrite={writable}
          load={(lang) => actions.tools({ ...ids, lang })}
          save={(key, enabled) => actions.setTool({ ...ids, key, enabled })}
          onClose={() => {
            setToolsOpen(false);
            // Cuántas siguen encendidas: la nota de la fila lo dice.
            void load(true);
          }}
          onChanged={() => onChanged?.()}
          onOpenSettings={() => setToolsOpen(false)}
        />
      ) : null}
    </li>
  );
}

function AgendaIcon() {
  return (
    <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted ring-1 ring-foreground/10" data-slot="agenda-icon">
      <CalendarCheck aria-hidden="true" className="size-5 text-muted-foreground" />
    </span>
  );
}

/**
 * Qué dice la línea de la propuesta de su texto de citas (3.1, 3.3, 3.5):
 * escribiéndose, abierta, sin escribir (con «Reintentar»), sin partida, sin
 * propuesta por ser de instrucciones libres, o —con la agenda activa en un agente
 * estructurado y nada pendiente— «Pedir la propuesta». `null`: nada que decir.
 */
type TextLine = "running" | "open" | "failed" | "build_budget_exhausted" | "not_structured" | "ask";
function textLine(agenda: AgentAgenda, reason: AgentAgenda["proposal_reason"], canWrite: boolean): TextLine | null {
  if (proposalRunning(agenda)) return "running";
  if (agenda.proposal?.status === "open") return "open";
  if (proposalFailed(agenda)) return "failed";
  if (reason === "build_budget_exhausted" || reason === "not_structured") return reason;
  if (canWrite && agenda.draft.on && agenda.structured) return "ask";
  return null;
}

/** El contenido de la línea; la región `role="status"` que la envuelve está siempre montada. */
function TextLineContent({
  line,
  busy,
  canWrite,
  onProposal,
  onRetry,
  onAsk,
}: {
  line: TextLine | null;
  busy: boolean;
  canWrite: boolean;
  onProposal?: () => void;
  onRetry: () => void;
  onAsk: () => void;
}) {
  const t = useT();
  switch (line) {
    case "running":
      return (
        <p className="inline-flex min-w-0 items-center gap-2 text-sm text-pretty text-muted-foreground">
          <LoaderCircle aria-hidden="true" className="size-4 shrink-0 animate-spin motion-reduce:animate-none" />
          <span className="min-w-0">{t("agenda.proposal.running")}</span>
        </p>
      );
    case "open":
      return (
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <span className="min-w-0 flex-1 basis-48 text-pretty">{t("agenda.proposal.open")}</span>
          {onProposal ? (
            <Button size="sm" variant="outline" onClick={onProposal}>
              {t("agenda.proposal.see")}
            </Button>
          ) : null}
        </div>
      );
    case "failed":
      return (
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <span className="min-w-0 flex-1 basis-48 text-pretty text-muted-foreground">{t("agenda.proposal.failed")}</span>
          {canWrite ? (
            <Button size="sm" variant="outline" disabled={busy} onClick={onRetry}>
              {t("agenda.row.retry")}
            </Button>
          ) : null}
        </div>
      );
    case "build_budget_exhausted":
    case "not_structured":
      return <p className="text-sm text-pretty text-muted-foreground">{t(`agenda.proposal.${line}`)}</p>;
    case "ask":
      return (
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <span className="min-w-0 flex-1 basis-48 text-pretty text-muted-foreground">{t("agenda.proposal.ask")}</span>
          <Button size="sm" variant="outline" disabled={busy} loading={busy} onClick={onAsk}>
            {t("agenda.review.propose")}
          </Button>
        </div>
      );
    default:
      return null;
  }
}

/**
 * «La agenda aún no está lista» (spec 057, 4.1 y 4.4): qué le falta a Reservas y
 * dónde se completa. Lo comparten la fila de la agenda, la ficha del agente y la
 * revisión. El horario y los servicios, en Negocio; encender Reservas, en Acceso;
 * el equipo y las plazas los da de alta el cliente en su Reservas.
 */
export function AgendaNotReady({ refId, missing }: { refId: string; missing: readonly string[] }) {
  const t = useT();
  return (
    <div className="min-w-0" data-slot="agenda-not-ready">
      <Callout tone="warning" title={t("agenda.notReady.title")}>
        <div className="grid min-w-0 gap-2">
          <p className="text-pretty">{t("agenda.notReady.body")}</p>
          <NotReadyList refId={refId} missing={missing} />
        </div>
      </Callout>
    </div>
  );
}

/** Lo que falta, cada cosa con dónde se completa. Sin nada que decir, nada. */
export function NotReadyList({ refId, missing }: { refId: string; missing: readonly string[] }) {
  const t = useT();
  const reasons = notReadyReasons(missing);
  if (!reasons.length) return null;
  return (
    <ul className="grid min-w-0 gap-2" data-slot="agenda-reasons">
      {reasons.map((code) => {
        const link = reasonLink(refId, code);
        return (
          <li key={code} className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1" data-reason={code}>
            <span className="grid min-w-0 flex-1 basis-48 gap-1">
              <span className="min-w-0 font-medium text-pretty break-words">{t(reasonKey(code))}</span>
              {completedByClient(code) ? <span className="text-xs text-pretty text-muted-foreground">{t("agenda.notReady.inClient")}</span> : null}
            </span>
            {link ? (
              <Link href={link.href} className={buttonVariants({ size: "sm", variant: "outline", className: "shrink-0" })}>
                {t(link.label)}
              </Link>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
