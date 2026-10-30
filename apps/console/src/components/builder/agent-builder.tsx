"use client";

import { ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Callout, StatusBadge, Tabs, TabsContent, TabsList, TabsTrigger } from "@nexus/ui";

import { builderDraftAction, decideProposalAction, saveAgentSpecAction } from "@/app/(console)/clients/[ref]/agents/builder-actions";
import { agentHeaderAction } from "@/app/(console)/clients/[ref]/agents/life-actions";
import { DraftConflictNotice } from "@/components/agent-draft/conflict-notice";
import { AgentCapForm } from "@/components/money/agent-cap";
import type { MetaSignupConfig } from "@/components/channels/whatsapp-connect";
import { CrumbName } from "@/components/shell/crumb-names";
import { useT } from "@/i18n/client";
import type { DraftChange } from "@/lib/backend/agent-draft-types";
import type { ClientAgent } from "@/lib/backend";
import type { AgentConversationPage, AgentPerformance, Improvements } from "@/lib/backend/agent-improve-types";
import type { AgentKnowledge } from "@/lib/backend/agent-knowledge-types";
import type { AgentHeader } from "@/lib/backend/agent-life-types";
import type { HistoryEntry, PlaygroundSession, PublishPreview, TestSuite } from "@/lib/backend/agent-quality-types";
import type { AgentSpec, BuilderDraft, EditableBlock, Proposal, SpecProblem } from "@/lib/backend/builder-types";
import type { AgentConnector } from "@/lib/backend/agent-connectors-types";
import type { AgentChannels, ChannelChange, ChannelPage } from "@/lib/backend/channel-config-types";
import type { Currency, Money } from "@/lib/backend/money-types";
import { agentHref } from "@/components/shell/routes-v2";
import { ShellBackButton } from "@/components/shell/shell-back-button";

import { AgentChannelsPanel, type AgentChannelsActions } from "./agent-channels";
import { AgentConnectorsPanel, type AgentConnectorsActions, type AgentConnectorsHandle } from "./agent-connectors";
import { AgentHistory, type HistoryActions } from "./agent-history";
import { AgentImprovementsPanel, type ImprovementsActions } from "./agent-improvements";
import { AgentKnowledgePanel, type AgentKnowledgeActions } from "./agent-knowledge";
import { AgentMenu, type AgentLifeActions } from "./agent-menu";
import { AgentPerformancePanel, type PerformanceActions } from "./agent-performance";
import { AgentPlayground, type PlaygroundActions } from "./agent-playground";
import { inMore, rowOfBlock, rowOfSection, type AgentRow } from "./agent-proto-model";
import { AgentRows, type BusinessSummary, type OpenRow } from "./agent-rows";
import { BlockEditor } from "./block-editor";
import { PendingQuestions, answerQuestion, type AnswerQuestion, type PendingQuestionsView } from "./builder-questions";
import { blockTitleKey } from "./block-view";
import { AGENT_BLOCKS, blockOfPointer, isEditable, tabOfSection, withBlock, type AgentBlockKey, type AgentTab, type Result } from "./builder-model";
import { rowState } from "./connector-model";
import { ChannelConfigPage, type ChannelBalance, type ChannelPageActions } from "./channel-page";
import { CopilotPanel, type CopilotActions, type CopilotHandle } from "./copilot-panel";
import { receptionOf, type Reception } from "./improve-model";
import { visibleText, visibleTone } from "./life-model";
import { MissingCapabilities, type MissingState } from "./missing-capabilities";
import { missingCapabilities, notOfferedKeys, specProblemText } from "./missing-model";
import { ProposalList, type DecideProposal } from "./proposals";
import { PublishBar, type PublishActions } from "./publish-bar";
import { ReceptionBadge, ReceptionSection } from "./reception-section";
import { ReviewPanel, useAgentReview, type ReviewActions } from "./review-panel";
import { TestList, type TestListActions } from "./test-list";
import { TestsBox, useTestRun } from "./tests-box";

/** Lo que la pantalla lee además del borrador (historias 8 y 9); `null` lo que no se pudo leer. */
export type AgentQuality = {
  tests: TestSuite | null;
  preview: PublishPreview | null;
  history: HistoryEntry[] | null;
  sessions: PlaygroundSession[] | null;
};

/** Las acciones de cada parte, para los tests; sin ellas, las de servidor. */
export type AgentQualityActions = {
  playground?: PlaygroundActions;
  tests?: TestListActions;
  review?: ReviewActions;
  publish?: PublishActions;
  history?: HistoryActions;
  life?: AgentLifeActions;
  copilot?: CopilotActions;
  knowledge?: AgentKnowledgeActions;
  channels?: AgentChannelsActions;
  performance?: PerformanceActions;
  improvements?: ImprovementsActions;
  connectors?: AgentConnectorsActions;
  channelPage?: ChannelPageActions;
  wait?: (ms: number) => Promise<void>;
};

/** La sección Conocimiento (historia 22): `data` nulo si no se pudo leer. Sin ella, no se pinta. */
export type AgentKnowledgeView = { data: AgentKnowledge | null; canWrite: boolean };
/** La sección Canales (historias 10 y 11): los números, la página de cada uno para su ⋯ y el enlace del dueño. */
export type AgentChannelsView = {
  data: AgentChannels | null;
  pages: Record<string, ChannelPage | null>;
  canWrite: boolean;
  /** Spec 047 (31.3): «desde su teléfono», solo con la bandera. */
  fromPhone: boolean;
  /** El alta de Meta de este entorno, para «Conectar WhatsApp» desde la pestaña (`agente.md` §10.1). */
  meta?: MetaSignupConfig | null;
};
/**
 * Spec 047 (63.1; H5): la configuración de un canal abierta dentro del agente
 * (`?canal=`): su página, su historial (`null` si no llegó), si se puede
 * cambiar y cómo se pide o se asigna saldo desde sus comprobaciones.
 */
export type AgentChannelConfigView = { page: ChannelPage; history: ChannelChange[] | null; canWrite: boolean; balance: ChannelBalance | null };
/**
 * Spec 047 (historia 31): Rendimiento —las cifras de 30 días, nulas si no se
 * pudieron leer— y las conversaciones con solo metadatos (`undefined` si esta
 * persona no puede leerlas; `null` si no llegaron).
 */
export type AgentPerformanceView = { performance: AgentPerformance | null; conversations?: AgentConversationPage | null };
/** Spec 047 (historias 31 y 32): las sugerencias y las correcciones de comportamiento; `null` si no llegaron. */
export type AgentImprovementsView = { data: Improvements | null };
/**
 * Spec 047 (historia 21): la sección Conectores. `data` en `undefined` se lee al
 * montar (llama al catálogo del proveedor y no frena la pantalla); `null`, no llegó.
 */
export type AgentConnectorsView = { data?: AgentConnector[] | null; canWrite: boolean };
/**
 * Spec 047 (44.1): Agente › Avanzado, con el tope mensual del agente en la
 * moneda de la bolsa de su cliente, y lo gastado este mes. `cap` en `undefined`
 * es que no se sabe el de hoy (la cabecera del agente no llegó).
 */
export type AgentAdvancedView = { cap: Money | null | undefined; spent?: Money | null; currency: Currency; canWrite: boolean };

export type AgentBuilderActions = {
  save: (body: { ref: string; agent: string; revision: number; spec: AgentSpec }) => Promise<Result<BuilderDraft>>;
  reload: (body: { ref: string; agent: string }) => Promise<Result<{ draft: BuilderDraft; proposals: Proposal[] | null }>>;
  decide: DecideProposal;
  /** La cabecera (estado visible, por defecto…), que cambia al guardar. */
  header?: (body: { ref: string; agent: string }) => Promise<Result<AgentHeader>>;
  /** Responder una pregunta que dejó el borrador de «Nuevo agente». */
  answer?: AnswerQuestion;
};

const SERVER_ACTIONS: AgentBuilderActions = {
  save: (body) => saveAgentSpecAction(body),
  reload: (body) => builderDraftAction(body),
  decide: (body) => decideProposalAction(body),
  header: (body) => agentHeaderAction(body),
  answer: answerQuestion,
};

/** Lo que la API registra al escribir el AgentSpec: compila el prompt del borrador. */
const SPEC_FIELDS = ["system_prompt"] as const;

type Conflict = { current: BuilderDraft; changes: DraftChange[]; block: EditableBlock; value: unknown };

/**
 * La pantalla del agente con la consola nueva (spec 047, historia 7; requisito
 * 17.7): el borrador por bloques —qué hace, cómo habla, instrucciones,
 * procedimientos, qué sabe, qué puede hacer, cuándo pasa a una persona y
 * reglas— cada uno editable en línea, sin pantalla «Revisar» aparte.
 *
 * Guardar un bloque escribe el AgentSpec entero en el único borrador del
 * agente con la revisión que leyó la pantalla (`If-Match`). Si otra persona
 * guardó antes, el aviso de conflicto de siempre enseña los dos cambios y nada
 * se pierde. Si el validador lo rechaza (`spec_invalid`), se dice qué y el
 * bloque sigue abierto con lo escrito. Cada edición deja las pruebas sin
 * ejecutar, y la cabecera lo cuenta. Al lado, las propuestas abiertas.
 *
 * Spec 047, historias 8 y 9 (T089, T094): arriba, la barra de «Guardar» (que
 * prueba, revisa y decide); a la derecha, el probador con hora y agenda de
 * mentira; debajo de los bloques, las pruebas, la revisión y el historial.
 * Cuando el borrador cambia (un bloque, una propuesta, una restauración, una
 * publicación) cada parte se vuelve a leer.
 *
 * Quien solo lee lo ve todo, sin «Editar» ni «Aplicar» (§V).
 *
 * «Configuración» es la pantalla del prototipo aprobado
 * (`specs/047-…/evidence/prototipo/agente.md` §4 y §5): a la izquierda la
 * tabla de cinco filas —cada una con los editores de sus bloques— y, plegado
 * debajo, «Más ajustes» con todo lo que el prototipo no enseña (Recepción, cada
 * prueba, la revisión entera, el historial, Avanzado, el copiloto y las
 * propuestas); a la derecha, pegada al bajar, la tarjeta de pruebas y el chat
 * de prueba; abajo, la barra flotante de vidrio.
 *
 * Enmienda del 2026-10-30 «Solo lo que tenemos» (T228; 65.3, 65.4, 65.8 y
 * 65.9): encima de la tabla, «No tenemos herramienta para: …» con el
 * `missing_capabilities` del borrador (se vuelve a leer con él, y si no se
 * puede, lo dice); una promesa sin herramienta lleva a su bloque. Nada de eso
 * lleva «Conectar {X}», ni en «Qué puede hacer» ni en los arreglos de la
 * revisión. La puerta sin pruebas que le apliquen abre «Añadir una prueba».
 */
export function AgentBuilder({
  refId,
  draft: initial,
  proposals: initialProposals,
  canWrite,
  quality,
  header: initialHeader,
  agents = [],
  knowledge,
  channels,
  advanced,
  performance,
  improvements,
  connectors,
  channelConfig = null,
  channelUnavailable = false,
  initialSection = null,
  clientName = null,
  business = null,
  questions = null,
  actions = SERVER_ACTIONS,
  qualityActions = {},
}: {
  refId: string;
  draft: BuilderDraft;
  proposals: Proposal[] | null;
  canWrite: boolean;
  quality?: AgentQuality;
  /** La cabecera con la vida del agente (historias 19 y 20); sin ella, la de T081. */
  header?: AgentHeader | null;
  /** Los agentes del cliente: los números de este y a quién pueden ir al archivarlo. */
  agents?: ClientAgent[];
  /** Spec 047 (historia 22): el conocimiento propio del agente, si esta persona puede leerlo. */
  knowledge?: AgentKnowledgeView;
  /** Spec 047 (historias 10 y 11): los números del agente, si esta persona puede leerlos. */
  channels?: AgentChannelsView;
  /** Spec 047 (44.1): «Avanzado», con el tope mensual del agente. */
  advanced?: AgentAdvancedView;
  /** Spec 047 (historia 31): la pestaña Rendimiento. Sin ella, no se pinta. */
  performance?: AgentPerformanceView;
  /** Spec 047 (historias 31 y 32): las Mejoras. Sin ellas, no se pintan. */
  improvements?: AgentImprovementsView;
  /** Spec 047 (historia 21): los Conectores del agente. Sin ellos, no se pintan. */
  connectors?: AgentConnectorsView;
  /** Spec 047 (63.1; H5): el canal que se configura dentro de la pestaña Canales (`?canal=`). */
  channelConfig?: AgentChannelConfigView | null;
  /** T218: se pidió un canal (`?canal=`) que no se pudo leer; la pestaña Canales lo dice sobre la lista. */
  channelUnavailable?: boolean;
  /** Spec 047 (49.6): la sección a la que llega un aviso (`?tab=`), ya traducida a su id. */
  initialSection?: string | null;
  /** El cliente del agente: «de Flor y Encanto» bajo el título. */
  clientName?: string | null;
  /** Lo que dice la ficha del negocio para «Qué sabe» (servicios, sedes, horario). */
  business?: BusinessSummary | null;
  /**
   * Las preguntas que dejó el borrador de «Nuevo agente» (`?job=`), encima de la
   * tabla mientras falten (prototipo §3.3). Sin ellas, no se pintan.
   */
  questions?: PendingQuestionsView | null;
  actions?: AgentBuilderActions;
  qualityActions?: AgentQualityActions;
}) {
  const t = useT();
  const [draft, setDraft] = React.useState(initial);
  const [proposals, setProposals] = React.useState(initialProposals);
  const [proposalsVersion, setProposalsVersion] = React.useState(0);
  // La fila abierta de la tabla y el bloque que se edita dentro (uno a la vez).
  const [openRow, setOpenRow] = React.useState<OpenRow | null>(null);
  // «Más ajustes»: plegado, salvo que un enlace lleve a algo de dentro.
  const [moreOpen, setMoreOpen] = React.useState(() => inMore(initialSection));
  const [saving, setSaving] = React.useState(false);
  const [problems, setProblems] = React.useState<SpecProblem[]>([]);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [conflict, setConflict] = React.useState<Conflict | null>(null);
  // Sube cada vez que el borrador cambia: pruebas, revisión, «Guardar» e
  // historial se vuelven a leer.
  const [refreshKey, setRefreshKey] = React.useState(0);
  const bump = () => setRefreshKey((k) => k + 1);
  // Spec 047 (65.3, 65.4): lo que no tenemos sale del borrador; mientras se
  // vuelve a leer, un esqueleto, y si no se puede, se dice.
  const [missingState, setMissingState] = React.useState<MissingState>("ready");
  // «Añadir una prueba» desde la puerta (65.9): abre el formulario de la lista.
  const [addTest, setAddTest] = React.useState(0);
  const router = useRouter();
  const [header, setHeader] = React.useState(initialHeader ?? null);
  // Las preguntas sin responder, para la barra flotante.
  const [pendingQuestions, setPendingQuestions] = React.useState(questions?.questions.length ?? 0);
  const writable = canWrite && draft.allowed.includes("edit");
  const spec = draft.spec;
  const missing = React.useMemo(() => missingCapabilities(draft.missing_capabilities), [draft.missing_capabilities]);
  // Nada de lo que la API dice que no ofrecemos lleva «Conectar {X}» (65.3).
  const notOffered = React.useMemo(() => notOfferedKeys(missing), [missing]);

  // Spec 047 (63.2; H9): Rendimiento solo existe con una versión guardada.
  const hasPerf = draft.active_number != null && Boolean(performance || improvements);
  // Un agente «Listo · sin canal» abre en Canales; uno que ya atiende, en
  // Rendimiento; uno sin guardar, en «Configuración». Un aviso
  // (`?tab=advanced`…) o un enlace (`#agente-pruebas`) abre la pestaña de su
  // sección y la lleva a la vista. La pestaña elegida vale mientras el ancla
  // no cambie: un enlace nuevo manda.
  const hash = React.useSyncExternalStore(subscribeHash, readHash, () => "");
  const [chosen, setChosen] = React.useState<{ tab: AgentTab; hash: string } | null>(null);
  // Spec 047 (63.1; H5): un canal abierto (`?canal=`) se configura dentro de
  // la pestaña Canales. Llega uno nuevo: se abre y la pestaña va a Canales.
  // Cambiar de pestaña o «Decidir luego» lo cierra y quita `?canal=`.
  const canalId = channelConfig?.page.id ?? null;
  const [openCanal, setOpenCanal] = React.useState(canalId);
  const [seenCanal, setSeenCanal] = React.useState(canalId);
  if (seenCanal !== canalId) {
    setSeenCanal(canalId);
    setOpenCanal(canalId);
    if (canalId) setChosen({ tab: "channels", hash });
  }
  const showingChannel = openCanal && channelConfig && channelConfig.page.id === openCanal ? channelConfig : null;
  // T218: el canal pedido no se pudo leer. Se abre la lista y se dice, hasta cambiar de pestaña.
  const [canalMissing, setCanalMissing] = React.useState(channelUnavailable && !channelConfig && Boolean(channels));
  // Lo último que guardó la configuración del canal: la lista lo refleja sin volver a leer.
  const [channelUpdate, setChannelUpdate] = React.useState<ChannelPage | null>(null);
  const tab: AgentTab =
    (chosen && chosen.hash === hash ? chosen.tab : null) ??
    (showingChannel || canalMissing ? "channels" : null) ??
    tabOfSection(hash) ??
    tabOfSection(initialSection) ??
    (header?.visible_state.code === "ready_no_channel" && channels ? "channels" : hasPerf ? "perf" : "build");
  function setTab(next: AgentTab) {
    if (showingChannel) closeChannel();
    if (canalMissing) {
      setCanalMissing(false);
      router.replace(agentHref(refId, draft.agent_id), { scroll: false });
    }
    setChosen({ tab: next, hash });
  }
  /** Cierra la configuración del canal: vuelve la lista y la dirección pierde `?canal=`. */
  function closeChannel() {
    setOpenCanal(null);
    router.replace(agentHref(refId, draft.agent_id), { scroll: false });
  }
  // La sección a la que hay que ir cuando su pestaña ya esté a la vista.
  const scrollTo = React.useRef<string | null>(initialSection);
  const followed = React.useRef("");
  // Pintar otra vez para que el efecto lleve la vista a `id` (aunque nada más cambie).
  const [tick, nudge] = React.useReducer((n: number) => n + 1, 0);
  function go(id: string) {
    scrollTo.current = id;
    nudge();
  }
  React.useEffect(() => {
    if (hash && hash !== followed.current && tabOfSection(hash)) {
      followed.current = hash;
      scrollTo.current = hash;
    }
    const id = scrollTo.current;
    if (!id) return;
    // Lo plegado se abre primero; se baja hasta ello en la pintura siguiente.
    if (inMore(id) && !moreOpen) return setMoreOpen(true);
    const row = rowOfSection(id);
    if (row && openRow?.row !== row) {
      const block = id.startsWith("bloque-") ? id.slice("bloque-".length) : null;
      return setOpenRow({ row, block: block && writable && isEditable(block) ? block : null });
    }
    scrollTo.current = null;
    const el = document.getElementById(id) ?? (row ? document.getElementById(`fila-${row}`) : null);
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "start" });
  }, [hash, moreOpen, openRow, writable, tick, tab]);
  const copilot = React.useRef<CopilotHandle>(null);

  /** La vida del agente cambió (pausa, nombre, por defecto…); archivado, la página es otra. */
  function onHeader(next: AgentHeader) {
    setHeader(next);
    bump();
    if (next.lifecycle === "archived") router.refresh();
  }

  /** «¿Por qué dijo esto?»: lo pregunta el copiloto, que vive en «Más ajustes», y la vista va a él. */
  function askWhy(context: { answer?: string; actions?: { tool: string; phrase: string }[]; test_id?: string }, about: string) {
    copilot.current?.ask(t("builder.copilot.why"), context, about);
    setMoreOpen(true);
    go("agente-copiloto");
  }

  /** Abrir una fila (con el editor de uno de sus bloques) o cerrarla. */
  function open(row: AgentRow | null, block: EditableBlock | null = null) {
    setOpenRow(row ? { row, block } : null);
    setProblems([]);
    setSaveError(null);
    setConflict(null);
  }

  async function save(block: EditableBlock, value: unknown, base: BuilderDraft = draft) {
    if (!base.spec) return;
    setSaving(true);
    setProblems([]);
    setSaveError(null);
    const next = withBlock(base.spec, block, value as AgentSpec[EditableBlock]);
    const res = await actions.save({ ref: refId, agent: base.agent_id, revision: base.revision, spec: next });
    setSaving(false);
    if (res.ok) {
      setDraft(res.data);
      setConflict(null);
      // Como el prototipo: guardar cierra la fila.
      setOpenRow(null);
      bump();
      toast.success(t("builder.edit.saved"));
      return;
    }
    if (res.status === 412 && res.code === "revision_conflict" && res.info?.current) {
      setConflict({ current: res.info.current as BuilderDraft, changes: (res.info.changes as DraftChange[] | undefined) ?? [], block, value });
      return;
    }
    if (res.code === "spec_invalid") {
      const list = res.info?.problems;
      setProblems(Array.isArray(list) ? (list as SpecProblem[]) : []);
      if (!Array.isArray(list) || !list.length) setSaveError(t("builder.edit.failed"));
      return;
    }
    setSaveError(res.status === 401 || res.status === 403 ? t("common.forbidden") : t("builder.edit.failed"));
  }

  /**
   * Spec 047 (53.1): la sección Recepción del AgentSpec, con la misma revisión
   * que los bloques. La sección dice sus errores; aquí solo se guarda y se avisa.
   */
  async function saveReception(next: Reception): Promise<Result<BuilderDraft>> {
    if (!draft.spec) return { ok: false, status: 409, message: "no spec" };
    const res = await actions.save({ ref: refId, agent: draft.agent_id, revision: draft.revision, spec: { ...draft.spec, reception: next } });
    if (res.ok) {
      setDraft(res.data);
      bump();
      toast.success(t("builder.edit.saved"));
    }
    return res;
  }

  /** Lo suyo: el bloque que se estaba guardando, encima del borrador de ahora. */
  function keepMine() {
    if (conflict) void save(conflict.block, conflict.value, conflict.current);
  }

  function keepTheirs() {
    if (!conflict) return;
    setDraft(conflict.current);
    open(null);
  }

  async function reload() {
    setMissingState("loading");
    const res = await actions.reload({ ref: refId, agent: draft.agent_id });
    if (!res.ok) {
      setMissingState("failed");
      return;
    }
    setDraft(res.data.draft);
    setProposals(res.data.proposals);
    setProposalsVersion((v) => v + 1);
    setMissingState("ready");
  }

  /** El borrador cambió fuera de los bloques: se lee otra vez, y todo lo demás. */
  async function refreshAll() {
    await reload();
    // Guardar cambia el estado visible («Borrador» → «Listo · sin canal»…).
    if (header && actions.header) {
      const next = await actions.header({ ref: refId, agent: draft.agent_id });
      if (next.ok) setHeader(next.data);
    }
    bump();
  }

  /** Abrir un bloque desde un arreglo (su fila, con su editor) y llevar la vista a él. */
  function openAt(key: string | null) {
    const block = (AGENT_BLOCKS as readonly string[]).includes(key ?? "") ? (key as AgentBlockKey) : null;
    const row = block ? rowOfBlock(block) : null;
    if (row) open(row, block && writable && isEditable(block) ? block : null);
    setTab("build");
    go(block ? `bloque-${block}` : "agente-borrador");
  }

  /** La puerta no guarda un agente sin pruebas que le apliquen (65.9): a la lista, con su formulario abierto. */
  function addTestFromGate() {
    setTab("build");
    setMoreOpen(true);
    setAddTest((n) => n + 1);
    go("agente-pruebas");
  }

  // Spec 047 (62.3; H11): «Conectar {X}» —de una habilidad o de un hallazgo—
  // abre aquí mismo el diálogo de conectar de la pestaña Conectores. Si el
  // conector no está en su catálogo, se va a la pestaña.
  const connectorsPanel = React.useRef<AgentConnectorsHandle>(null);
  const [inUse, setInUse] = React.useState<ReadonlySet<string>>(() => new Set());
  const connectTo = connectors
    ? (integration?: string) => {
        if (integration && connectorsPanel.current?.connect(integration)) return;
        setTab("connectors");
        go("agente-conectores");
      }
    : undefined;
  /** «Conectar un canal»: la pestaña Canales. Sin ella, la barra lleva a la página de canales del cliente. */
  const channelsTab = channels
    ? () => {
        setTab("channels");
        go("agente-canales");
      }
    : undefined;

  // Las pruebas y la revisión de la columna derecha; «Más ajustes» y la barra leen lo mismo.
  const testRun = useTestRun({
    refId,
    agentId: draft.agent_id,
    initial: quality?.tests ?? null,
    canWrite: writable,
    refreshKey,
    onChanged: () => void refreshAll(),
    actions: qualityActions.tests,
    wait: qualityActions.wait,
    enabled: Boolean(quality),
  });
  const review = useAgentReview({
    refId,
    agentId: draft.agent_id,
    refreshKey,
    onApplied: () => void refreshAll(),
    actions: qualityActions.review,
    enabled: Boolean(quality),
  });

  const versions = (quality?.history ?? [])
    .filter((v) => v.status === "active" || (v.status === "archived" && v.published_at))
    .map((v) => v.number);

  /** El editor de un bloque dentro de su fila, con lo que dijo la API al guardar. */
  function editor(key: EditableBlock) {
    if (!spec) return null;
    return (
      <div className="grid min-w-0 gap-3">
        {conflict ? (
          <DraftConflictNotice current={conflict.current} changes={conflict.changes} mine={SPEC_FIELDS} busy={saving} onKeepMine={keepMine} onKeepTheirs={keepTheirs} />
        ) : null}
        {problems.length ? (
          <Callout tone="danger" title={t("builder.edit.problems")}>
            <ul className="grid list-disc gap-1 pl-5" data-slot="spec-problems">
              {problems.map((p, i) => (
                <li key={`${p.pointer}-${i}`} className="break-words">
                  {specProblemText(p, spec, t)}
                </li>
              ))}
            </ul>
          </Callout>
        ) : null}
        {saveError ? (
          <p role="alert" className="text-sm text-destructive">
            {saveError}
          </p>
        ) : null}
        <BlockEditor
          block={key}
          spec={spec}
          busy={saving}
          label={t("builder.edit.label", { block: t(blockTitleKey(key)) })}
          onSave={(value) => void save(key, value)}
          onCancel={() => open(null)}
        />
      </div>
    );
  }

  const blocks = spec ? (
    // Como el prototipo: cinco filas con su lápiz; los 9 bloques del AgentSpec dentro.
    <AgentRows
      refId={refId}
      spec={spec}
      canEdit={writable}
      open={openRow}
      onOpen={(row, block) => open(row, block)}
      onClose={() => open(null)}
      editor={editor}
      knowledge={
        knowledge ? (
          <AgentKnowledgePanel
            refId={refId}
            agentId={draft.agent_id}
            agentName={header?.name ?? draft.agent_name}
            knowledge={knowledge.data}
            canWrite={knowledge.canWrite}
            onTaught={() => void refreshAll()}
            actions={qualityActions.knowledge}
          />
        ) : undefined
      }
      sources={knowledge?.data ? knowledge.data.items.length : null}
      business={business}
      onConnect={connectTo}
      connected={inUse}
      notOffered={notOffered}
    />
  ) : (
    <Callout tone="info">{t("builder.agent.noSpec")}</Callout>
  );

  const openProposals = proposals?.length ?? 0;
  const improvementsPanel = improvements ? (
    <AgentImprovementsPanel
      refId={refId}
      agentId={draft.agent_id}
      improvements={improvements.data}
      onAccepted={() => void refreshAll()}
      actions={qualityActions.improvements}
    />
  ) : null;

  // El owner (2026-10-28): las pestañas del agente no llevan números.
  const tabs: { id: AgentTab; label: string }[] = [
    ...(hasPerf ? [{ id: "perf" as const, label: t("improve.performance.title") }] : []),
    { id: "build", label: t("builder.screen.tab.build") },
    ...(channels ? [{ id: "channels" as const, label: t("builder.screen.channels") }] : []),
    ...(connectors ? [{ id: "connectors" as const, label: t("agentConn.title") }] : []),
  ];
  const shown = tabs.some((x) => x.id === tab) ? tab : "build";
  // Como el prototipo: «Publicado · de Flor y Encanto», justo después del estado.
  const ofClient = clientName ? (
    <>
      <span aria-hidden="true" className="text-muted-foreground">
        ·
      </span>
      <span className="text-base text-muted-foreground">{t("builder.agent.ofClient", { name: clientName })}</span>
    </>
  ) : null;

  return (
    <div className="grid min-w-0 gap-6" data-slot="agent-builder">
      <CrumbName id={draft.agent_id} label={draft.agent_name} />
      {/* Como el prototipo aprobado: el agente es el título de la página, con su
          estado y de qué cliente es, y debajo sus pestañas en vidrio. */}
      <header className="grid min-w-0 gap-2 border-b border-border pb-5">
        <div className="flex min-w-0 items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <ShellBackButton />
            <h1 className="min-w-0 text-2xl font-semibold tracking-tighter text-balance break-words sm:text-display">{header?.name ?? draft.agent_name}</h1>
          </div>
          {header ? (
            <AgentMenu
              refId={refId}
              header={header}
              agents={agents}
              onHeader={onHeader}
              onArchived={onHeader}
              actions={qualityActions.life}
            />
          ) : null}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
          {header ? (
            <>
              {/* Spec 047 (25.5): el estado visible de la API, el mismo en toda la consola. */}
              <StatusBadge tone={visibleTone(header.visible_state)} data-slot="agent-state">
                {visibleText(t, header.visible_state)}
              </StatusBadge>
              {ofClient}
              {header.is_default ? <span className="text-muted-foreground">{t("builder.agents.principal")}</span> : null}
              <ReceptionBadge published={header.is_reception} drafted={receptionOf(spec).enabled} />
              {draft.exists && draft.number && draft.active_number ? <StatusBadge tone="info">{t("builder.agent.draft", { n: draft.number })}</StatusBadge> : null}
            </>
          ) : (
            <>
              {draft.exists && draft.number ? <StatusBadge tone="info">{t("builder.agent.draft", { n: draft.number })}</StatusBadge> : null}
              {draft.active_number ? (
                <StatusBadge tone="positive">{t("builder.agent.published", { n: draft.active_number })}</StatusBadge>
              ) : (
                <StatusBadge tone="muted">{t("builder.agent.unpublished")}</StatusBadge>
              )}
              {ofClient}
            </>
          )}
          {!draft.exists && draft.active_number ? <span className="text-muted-foreground">{t("builder.agent.noDraft")}</span> : null}
          <TestsLine tests={draft.tests} />
        </div>
        {header?.visible_state.code === "paused" ? <Callout tone="warning">{t("builder.life.paused")}</Callout> : null}
      </header>

      <Tabs value={shown} onValueChange={(value) => setTab(value as AgentTab)} className="min-w-0 flex-col gap-6">
        <TabsList floating aria-label={t("builder.screen.sections")}>
          {tabs.map((x) => (
            <TabsTrigger key={x.id} value={x.id}>
              {x.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Las pestañas ocultas siguen montadas: el chat de prueba o un editor
            abierto no se pierden al cambiar de pestaña. */}
        {hasPerf ? (
          // Como el prototipo (§6, H9): los 30 días y las sugerencias arriba, en dos columnas; la gráfica y las conversaciones debajo.
          <TabsContent value="perf" keepMounted className="grid min-w-0 gap-4">
            {performance ? (
              <AgentPerformancePanel
                refId={refId}
                agentId={draft.agent_id}
                performance={performance.performance}
                conversations={performance.conversations}
                cap={advanced?.cap ?? null}
                suggestions={improvementsPanel}
                actions={qualityActions.performance}
              />
            ) : (
              improvementsPanel
            )}
          </TabsContent>
        ) : null}

        <TabsContent value="build" keepMounted className="grid min-w-0 gap-5">
          {/* Como el prototipo (§4.1): dos columnas desde 1060 px; la derecha, pegada al bajar. */}
          <div className={quality ? "grid min-w-0 items-start gap-5 min-[1060px]:grid-cols-[minmax(0,1fr)_minmax(360px,440px)]" : "grid min-w-0 gap-5"}>
            <div className="grid min-w-0 gap-4">
              {questions && questions.questions.length ? (
                // Como el prototipo (§3.3): lo que le falta al borrador, encima de la tabla.
                <div id="agente-preguntas" className="min-w-0 scroll-mt-24">
                  <PendingQuestions
                    refId={refId}
                    view={questions}
                    canWrite={writable}
                    answer={actions.answer ?? answerQuestion}
                    onAnswered={() => void refreshAll()}
                    onPending={setPendingQuestions}
                  />
                </div>
              ) : null}
              <div id="agente-faltan" className="min-w-0 scroll-mt-24 empty:hidden">
                <MissingCapabilities
                  items={missing}
                  state={missingState}
                  canEdit={writable}
                  onEdit={(pointer) => openAt(blockOfPointer(pointer))}
                  onRetry={reload}
                />
              </div>
              <div id="agente-borrador" className="min-w-0 scroll-mt-24">
                {blocks}
              </div>
              <MoreSettings open={moreOpen} onToggle={() => setMoreOpen((v) => !v)} proposals={openProposals}>
                {spec ? (
                  <ScreenSection id="agente-recepcion" title={t("reception.title")}>
                    <ReceptionSection
                      key={draft.revision}
                      agentId={draft.agent_id}
                      reception={receptionOf(spec)}
                      agents={agents}
                      canWrite={writable}
                      onSave={saveReception}
                      onReload={() => void reload()}
                    />
                  </ScreenSection>
                ) : null}
                {quality ? (
                  <>
                    <ScreenSection id="agente-pruebas" title={t("builder.screen.tests")}>
                      <TestList
                        refId={refId}
                        agentId={draft.agent_id}
                        suite={quality.tests}
                        canWrite={writable}
                        refreshKey={refreshKey}
                        structured={spec?.mode === "structured"}
                        addRequest={addTest}
                        onFix={() => openAt("instructions")}
                        onWhy={(test) => askWhy({ test_id: test.id }, t("builder.copilot.about.test", { name: test.name }))}
                        onChanged={() => void refreshAll()}
                        actions={qualityActions.tests}
                        wait={qualityActions.wait}
                      />
                    </ScreenSection>
                    <ScreenSection id="agente-revision" title={t("builder.screen.review")}>
                      <ReviewPanel
                        refId={refId}
                        agentId={draft.agent_id}
                        canWrite={writable}
                        refreshKey={refreshKey}
                        onEdit={(pointer) => openAt(pointer ? blockOfPointer(pointer) : null)}
                        onApplied={() => void refreshAll()}
                        source={review}
                      />
                    </ScreenSection>
                    <ScreenSection id="agente-historial" title={t("builder.screen.history")}>
                      <AgentHistory
                        refId={refId}
                        agentId={draft.agent_id}
                        history={quality.history}
                        canWrite={writable}
                        refreshKey={refreshKey}
                        onRestored={() => void refreshAll()}
                        actions={qualityActions.history}
                      />
                    </ScreenSection>
                  </>
                ) : null}
                <ScreenSection id="agente-avanzado" title={t("money.advanced.title")}>
                  {advanced ? (
                    <AgentCapForm
                      refId={refId}
                      agentId={draft.agent_id}
                      agentName={header?.name ?? draft.agent_name}
                      cap={advanced.cap}
                      spent={advanced.spent ?? null}
                      currency={advanced.currency}
                      canWrite={advanced.canWrite}
                    />
                  ) : null}
                  {/* Spec 047 (64.1; D55): sin «Calidad» ni «Fijar un modelo» mientras
                      Auphere gestiona los modelos. Un aviso viejo (`?tab=quality`) llega aquí. */}
                  <p
                    id="agente-calidad"
                    className="min-w-0 scroll-mt-24 border-t border-border pt-4 text-sm text-pretty text-muted-foreground first:border-t-0 first:pt-0"
                    data-slot="model-managed"
                  >
                    {t("modelQuality.managed")}
                  </p>
                </ScreenSection>
                {quality && spec ? (
                  <div id="agente-copiloto" className="min-w-0 scroll-mt-24 rounded-lg border border-border bg-card p-4 sm:p-6">
                    <CopilotPanel
                      ref={copilot}
                      refId={refId}
                      agentId={draft.agent_id}
                      canWrite={writable}
                      onChanged={() => void refreshAll()}
                      actions={qualityActions.copilot}
                    />
                  </div>
                ) : null}
                {spec ? (
                  <div id="agente-propuestas" className="min-w-0 scroll-mt-24 rounded-lg border border-border bg-card p-4 sm:p-6">
                    <ProposalList
                      key={proposalsVersion}
                      refId={refId}
                      agentId={draft.agent_id}
                      proposals={proposals}
                      canWrite={writable}
                      decide={actions.decide}
                      onApplied={() => void refreshAll()}
                      onRetry={() => void reload()}
                    />
                  </div>
                ) : null}
              </MoreSettings>
            </div>
            {quality ? (
              // Como el prototipo (§5), con el orden que pidió el owner (2026-10-28): el
              // chat de prueba arriba y, justo debajo, las pruebas con «Ejecutar todas».
              // Pegada al bajar, nunca más alta que lo que deja la barra flotante
              // (arriba 120 px, abajo la barra con su margen): la barra no tapa el
              // chat; si no cabe todo, lo de abajo se desplaza dentro de la columna.
              <aside
                aria-label={t("agentProto.aside")}
                className="grid min-w-0 content-start gap-3 min-[1060px]:sticky min-[1060px]:top-30 min-[1060px]:max-h-[calc(100dvh-13rem)] min-[1060px]:overflow-y-auto min-[1060px]:overscroll-contain"
              >
                <AgentPlayground
                  refId={refId}
                  agentId={draft.agent_id}
                  sessions={quality.sessions}
                  versions={versions}
                  hasDraft={draft.exists}
                  canWrite={writable}
                  onWhy={
                    spec
                      ? (turn) =>
                          askWhy(
                            { answer: turn.bubbles.join("\n"), actions: turn.actions },
                            t("builder.copilot.about.answer", { answer: excerpt(turn.bubbles.join(" ")) }),
                          )
                      : undefined
                  }
                  actions={qualityActions.playground}
                />
                <TestsBox
                  refId={refId}
                  tests={testRun}
                  review={review}
                  canWrite={writable}
                  onFix={() => openAt("instructions")}
                  onWhy={spec ? (test) => askWhy({ test_id: test.id }, t("builder.copilot.about.test", { name: test.name })) : undefined}
                  onEdit={(pointer) => openAt(pointer ? blockOfPointer(pointer) : null)}
                  onConnect={connectTo}
                  notOffered={notOffered}
                  onAll={() => {
                    setMoreOpen(true);
                    go("agente-pruebas");
                  }}
                />
              </aside>
            ) : null}
          </div>
          {quality ? (
            // La barra flotante de vidrio (§4.5): el estado a la izquierda, los botones píldora a la derecha.
            <div
              data-slot="agent-actionbar"
              className="glass sticky bottom-4 z-(--z-sticky) min-w-0 rounded-xl p-3 ring-1 ring-foreground/10 min-[560px]:rounded-full min-[560px]:py-2 min-[560px]:pr-2 min-[560px]:pl-4"
            >
              <PublishBar
                refId={refId}
                agentId={draft.agent_id}
                preview={quality.preview}
                hadActive={draft.active_number !== null}
                canWrite={writable}
                refreshKey={refreshKey}
                tests={{ summary: testRun.suite?.summary ?? null, running: testRun.running !== null, canRun: testRun.canRun, run: () => void testRun.run("all") }}
                pendingQuestions={pendingQuestions}
                onConnect={channelsTab}
                onAddTest={writable ? addTestFromGate : undefined}
                onEdit={writable ? (pointer) => openAt(blockOfPointer(pointer)) : undefined}
                onPublished={() => void refreshAll()}
                actions={qualityActions.publish}
                wait={qualityActions.wait}
              />
            </div>
          ) : null}
        </TabsContent>

        {channels ? (
          <TabsContent value="channels" keepMounted className="grid min-w-0 gap-6">
            {/* Como el prototipo (`agente.md` §7 y §8): sin marco ni título propio. Con
                un canal abierto (`?canal=`), su configuración; la lista sigue montada debajo, oculta. */}
            <div id="agente-canales" className="grid min-w-0 scroll-mt-24 gap-6">
              {canalMissing ? <Callout tone="warning">{t("builder.channel.page.unavailable")}</Callout> : null}
              {showingChannel ? (
                <ChannelConfigPage
                  key={showingChannel.page.id}
                  refId={refId}
                  agentId={draft.agent_id}
                  page={showingChannel.page}
                  history={showingChannel.history}
                  canWrite={showingChannel.canWrite}
                  balance={showingChannel.balance}
                  onClose={() => {
                    closeChannel();
                    setChosen({ tab: "channels", hash });
                  }}
                  onChanged={setChannelUpdate}
                  actions={qualityActions.channelPage}
                />
              ) : null}
              <div hidden={Boolean(showingChannel)} className="min-w-0">
                <AgentChannelsPanel
                  refId={refId}
                  agentId={draft.agent_id}
                  channels={channels.data}
                  pages={channels.pages}
                  canWrite={channels.canWrite}
                  fromPhone={channels.fromPhone}
                  clientName={clientName}
                  meta={channels.meta ?? null}
                  updated={channelUpdate}
                  actions={qualityActions.channels}
                />
              </div>
            </div>
          </TabsContent>
        ) : null}

        {connectors ? (
          <TabsContent value="connectors" keepMounted className="grid min-w-0 gap-6">
            {/* Como el prototipo (§9, H10): sin marco propio; la tarjeta de filas es la sección. */}
            <section id="agente-conectores" aria-labelledby="agente-conectores-title" className="grid min-w-0 scroll-mt-24 gap-3">
              <h2 id="agente-conectores-title" className="sr-only">
                {t("agentConn.title")}
              </h2>
              <AgentConnectorsPanel
                ref={connectorsPanel}
                refId={refId}
                agentId={draft.agent_id}
                connectors={connectors.data}
                canWrite={connectors.canWrite}
                spec={spec}
                onList={(list) => setInUse(new Set(list.filter((c) => rowState(c) === "on").map((c) => c.slug)))}
                onConnected={() => void refreshAll()}
                actions={qualityActions.connectors}
              />
            </section>
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}

/** El ancla de la URL (`#agente-pruebas` → `agente-pruebas`), como almacén externo. */
function subscribeHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function readHash(): string {
  return decodeURIComponent(window.location.hash.slice(1));
}

/** Las primeras palabras de una respuesta, para decir de cuál se pregunta. */
function excerpt(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** Una parte de la pantalla del agente con su título (h3) y su ancla. */
function ScreenSection({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="grid min-w-0 scroll-mt-24 gap-3 rounded-lg border border-border bg-card p-4 sm:p-6">
      <h2 id={`${id}-title`} className="text-base font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

/**
 * «Más ajustes» (§12): lo que el prototipo no enseña, plegado bajo la tabla.
 * Cerrado de entrada; un enlace a algo de dentro (`?tab=`, `#agente-…`) lo abre.
 * Lo de dentro sigue montado cerrado: nada de lo que se estaba haciendo se pierde.
 */
function MoreSettings({ open, onToggle, proposals, children }: { open: boolean; onToggle: () => void; proposals: number; children: React.ReactNode }) {
  const t = useT();
  const id = React.useId();
  return (
    <div className="grid min-w-0 gap-4" data-slot="more-settings">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={onToggle}
        className="flex w-full min-w-0 cursor-pointer items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 text-left transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:px-5"
      >
        <span className="grid min-w-0 gap-1">
          <span className="inline-flex min-w-0 flex-wrap items-center gap-2 text-sm font-medium">
            {t("agentProto.more")}
            {proposals ? (
              <StatusBadge tone="info">{proposals === 1 ? t("agentProto.more.proposals.one") : t("agentProto.more.proposals.other", { n: proposals })}</StatusBadge>
            ) : null}
          </span>
          <span className="text-xs text-pretty text-muted-foreground">{t("agentProto.more.hint")}</span>
        </span>
        <ChevronDown aria-hidden="true" className={`size-4 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
      </button>
      <div id={id} hidden={!open} className="grid min-w-0 gap-4">
        {children}
      </div>
    </div>
  );
}

/** «8 pruebas · 3 sin ejecutar»: editar un bloque deja las pruebas sin ejecutar (17.7). */
function TestsLine({ tests }: { tests: BuilderDraft["tests"] }) {
  const t = useT();
  if (!tests || tests.total === 0) return <span className="text-muted-foreground">{t("builder.tests.none")}</span>;
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-2" data-slot="builder-tests">
      <span>{t("builder.tests.total", { n: tests.total })}</span>
      {tests.stale > 0 ? <StatusBadge tone="warn">{t("builder.tests.stale", { n: tests.stale })}</StatusBadge> : null}
    </span>
  );
}
