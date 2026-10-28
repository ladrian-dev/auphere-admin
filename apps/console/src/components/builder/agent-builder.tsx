"use client";

import { Pencil } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, StatusBadge } from "@nexus/ui";

import { builderDraftAction, decideProposalAction, saveAgentSpecAction } from "@/app/(console)/clients/[ref]/agents/builder-actions";
import { DraftConflictNotice } from "@/components/agent-draft/conflict-notice";
import { AgentCapForm } from "@/components/money/agent-cap";
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
import type { AgentChannels, ChannelPage } from "@/lib/backend/channel-config-types";
import type { ModelPolicy, ModelQuality } from "@/lib/backend/model-quality-types";
import type { Currency, Money } from "@/lib/backend/money-types";

import { AgentChannelsPanel, type AgentChannelsActions } from "./agent-channels";
import { AgentConnectorsPanel, type AgentConnectorsActions } from "./agent-connectors";
import { AgentHistory, type HistoryActions } from "./agent-history";
import { AgentImprovementsPanel, type ImprovementsActions } from "./agent-improvements";
import { AgentKnowledgePanel, type AgentKnowledgeActions } from "./agent-knowledge";
import { AgentMenu, type AgentLifeActions } from "./agent-menu";
import { AgentModelQuality, type ModelQualityActions } from "./agent-model-quality";
import { AgentPerformancePanel, type PerformanceActions } from "./agent-performance";
import { AgentPlayground, type PlaygroundActions } from "./agent-playground";
import { BlockEditor } from "./block-editor";
import { BlockValue, blockTitleKey } from "./block-view";
import { AGENT_BLOCKS, blockFromSpec, blockOfPointer, isEditable, withBlock, type AgentBlockKey, type Result } from "./builder-model";
import { CopilotPanel, type CopilotActions, type CopilotHandle } from "./copilot-panel";
import { receptionOf, type Reception } from "./improve-model";
import { visibleText, visibleTone } from "./life-model";
import { draftPolicy } from "./model-quality-model";
import { ProposalList, type DecideProposal } from "./proposals";
import { PublishBar, type PublishActions } from "./publish-bar";
import { ReceptionBadge, ReceptionSection } from "./reception-section";
import { ReviewPanel, type ReviewActions } from "./review-panel";
import { TestList, type TestListActions } from "./test-list";

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
  modelQuality?: ModelQualityActions;
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
};
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
/** Spec 047 (historia 23): Avanzado › Calidad. `data` en `undefined` se lee al montar. */
export type AgentModelQualityView = { data?: ModelQuality | null; canWrite: boolean };

const SECTIONS = [
  { id: "agente-borrador", label: "builder.screen.blocks", part: "draft" },
  { id: "agente-conocimiento", label: "builder.screen.knowledge", part: "knowledge" },
  { id: "agente-canales", label: "builder.screen.channels", part: "channels" },
  { id: "agente-conectores", label: "agentConn.title", part: "connectors" },
  { id: "agente-recepcion", label: "reception.title", part: "reception" },
  { id: "agente-rendimiento", label: "improve.performance.title", part: "performance" },
  { id: "agente-mejoras", label: "improve.title", part: "improvements" },
  { id: "agente-pruebas", label: "builder.screen.tests", part: "quality" },
  { id: "agente-revision", label: "builder.screen.review", part: "quality" },
  { id: "agente-historial", label: "builder.screen.history", part: "quality" },
  { id: "agente-avanzado", label: "money.advanced.title", part: "advanced" },
] as const;

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
};

const SERVER_ACTIONS: AgentBuilderActions = {
  save: (body) => saveAgentSpecAction(body),
  reload: (body) => builderDraftAction(body),
  decide: (body) => decideProposalAction(body),
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
  modelQuality,
  initialSection = null,
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
  /** Spec 047 (historia 23): Avanzado › Calidad. Sin ella, no se pinta. */
  modelQuality?: AgentModelQualityView;
  /** Spec 047 (49.6): la sección a la que llega un aviso (`?tab=`), ya traducida a su id. */
  initialSection?: string | null;
  actions?: AgentBuilderActions;
  qualityActions?: AgentQualityActions;
}) {
  const t = useT();
  const [draft, setDraft] = React.useState(initial);
  const [proposals, setProposals] = React.useState(initialProposals);
  const [proposalsVersion, setProposalsVersion] = React.useState(0);
  const [editing, setEditing] = React.useState<EditableBlock | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [problems, setProblems] = React.useState<SpecProblem[]>([]);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [conflict, setConflict] = React.useState<Conflict | null>(null);
  // Sube cada vez que el borrador cambia: pruebas, revisión, «Guardar» e
  // historial se vuelven a leer.
  const [refreshKey, setRefreshKey] = React.useState(0);
  const bump = () => setRefreshKey((k) => k + 1);
  const router = useRouter();
  const [header, setHeader] = React.useState(initialHeader ?? null);

  // Un aviso que lleva a una sección (`?tab=advanced`…): se lleva a la vista al abrir.
  React.useEffect(() => {
    if (!initialSection) return;
    const target = document.getElementById(initialSection);
    if (target && typeof target.scrollIntoView === "function") target.scrollIntoView({ block: "start" });
  }, [initialSection]);
  const copilot = React.useRef<CopilotHandle>(null);

  /** La vida del agente cambió (pausa, nombre, por defecto…); archivado, la página es otra. */
  function onHeader(next: AgentHeader) {
    setHeader(next);
    bump();
    if (next.lifecycle === "archived") router.refresh();
  }

  /** «¿Por qué dijo esto?»: lo pregunta el copiloto y la vista va a él. */
  function askWhy(context: { answer?: string; actions?: { tool: string; phrase: string }[]; test_id?: string }, about: string) {
    copilot.current?.ask(t("builder.copilot.why"), context, about);
    document.getElementById("agente-copiloto")?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }

  const writable = canWrite && draft.allowed.includes("edit");
  const spec = draft.spec;

  function open(block: EditableBlock | null) {
    setEditing(block);
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
      setEditing(null);
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

  /**
   * Spec 047 (39.1): la calidad elegida va al borrador, con la misma revisión
   * que los bloques. Se aplica al «Guardar», que pasa la puerta.
   */
  async function saveModelPolicy(policy: ModelPolicy): Promise<Result<BuilderDraft>> {
    if (!draft.spec) return { ok: false, status: 409, message: "no spec" };
    const res = await actions.save({ ref: refId, agent: draft.agent_id, revision: draft.revision, spec: { ...draft.spec, model_policy: policy } });
    if (res.ok) {
      setDraft(res.data);
      bump();
    } else if (res.status === 412) {
      // Otra persona guardó antes: se lee su borrador y se puede volver a elegir.
      void reload();
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
    const res = await actions.reload({ ref: refId, agent: draft.agent_id });
    if (!res.ok) return;
    setDraft(res.data.draft);
    setProposals(res.data.proposals);
    setProposalsVersion((v) => v + 1);
  }

  /** El borrador cambió fuera de los bloques: se lee otra vez, y todo lo demás. */
  async function refreshAll() {
    await reload();
    bump();
  }

  /** Abrir un bloque desde un arreglo y llevar la vista a él. */
  function openAt(key: string | null) {
    const block = (AGENT_BLOCKS as readonly string[]).includes(key ?? "") ? (key as AgentBlockKey) : null;
    if (block && writable && isEditable(block)) open(block);
    const target = document.getElementById(block ? `bloque-${block}` : "agente-borrador");
    target?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  }

  const versions = (quality?.history ?? [])
    .filter((v) => v.status === "active" || (v.status === "archived" && v.published_at))
    .map((v) => v.number);

  const blocks = spec ? (
    <ol aria-label={t("builder.agent.blocks")} className="grid min-w-0 gap-4">
      {AGENT_BLOCKS.map((key) => (
        <BlockCard
          key={key}
          refId={refId}
          block={key}
          spec={spec}
          editing={editing === key}
          canEdit={writable && isEditable(key)}
          onEdit={() => open(isEditable(key) ? key : null)}
        >
          {editing === key && isEditable(key) ? (
            <div className="grid min-w-0 gap-3">
              {conflict ? (
                <DraftConflictNotice
                  current={conflict.current}
                  changes={conflict.changes}
                  mine={SPEC_FIELDS}
                  busy={saving}
                  onKeepMine={keepMine}
                  onKeepTheirs={keepTheirs}
                />
              ) : null}
              {problems.length ? (
                <Callout tone="danger" title={t("builder.edit.problems")}>
                  <ul className="grid list-disc gap-1 pl-5" data-slot="spec-problems">
                    {problems.map((p, i) => (
                      <li key={`${p.pointer}-${i}`} className="break-words">
                        {p.message || p.code}
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
          ) : null}
        </BlockCard>
      ))}
    </ol>
  ) : (
    <Callout tone="info">{t("builder.agent.noSpec")}</Callout>
  );

  return (
    <div className="grid min-w-0 gap-6" data-slot="agent-builder">
      <CrumbName id={draft.agent_id} label={draft.agent_name} />
      <header className="grid min-w-0 gap-3">
        <div className="grid min-w-0 gap-2">
          <div className="flex min-w-0 items-start justify-between gap-3">
            <h2 className="min-w-0 text-xl font-semibold text-balance break-words">{header?.name ?? draft.agent_name}</h2>
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
              </>
            )}
            {!draft.exists && draft.active_number ? <span className="text-muted-foreground">{t("builder.agent.noDraft")}</span> : null}
            <TestsLine tests={draft.tests} />
          </div>
          {header?.visible_state.code === "paused" ? <Callout tone="warning">{t("builder.life.paused")}</Callout> : null}
        </div>
        {quality ? (
          <div className="min-w-0 rounded-md border border-border bg-card p-3">
            <PublishBar
              refId={refId}
              agentId={draft.agent_id}
              preview={quality.preview}
              hadActive={draft.active_number !== null}
              canWrite={writable}
              refreshKey={refreshKey}
              onPublished={() => void refreshAll()}
              actions={qualityActions.publish}
              wait={qualityActions.wait}
            />
          </div>
        ) : null}
        {quality || knowledge || channels || connectors || advanced || modelQuality || performance || improvements || spec ? (
          <nav aria-label={t("builder.screen.sections")} className="min-w-0">
            <ul className="flex min-w-0 gap-2 overflow-x-auto pb-1" data-scroll-x>
              {SECTIONS.filter(
                (s) =>
                  s.part === "draft" ||
                  (s.part === "quality" && quality) ||
                  (s.part === "knowledge" && knowledge) ||
                  (s.part === "channels" && channels) ||
                  (s.part === "connectors" && connectors) ||
                  (s.part === "reception" && spec) ||
                  (s.part === "performance" && performance) ||
                  (s.part === "improvements" && improvements) ||
                  (s.part === "advanced" && (advanced || modelQuality)),
              ).map((section) => (
                <li key={section.id} className="shrink-0">
                  <a
                    href={`#${section.id}`}
                    className="inline-flex min-h-8 items-center rounded-full px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  >
                    {t(section.label)}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}
      </header>

      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:items-start">
        <div className="grid min-w-0 gap-8">
          <div id="agente-borrador" className="min-w-0 scroll-mt-24">
            {blocks}
          </div>
          {knowledge ? (
            <ScreenSection id="agente-conocimiento" title={t("builder.screen.knowledge")}>
              <AgentKnowledgePanel
                refId={refId}
                agentId={draft.agent_id}
                agentName={header?.name ?? draft.agent_name}
                knowledge={knowledge.data}
                canWrite={knowledge.canWrite}
                onTaught={() => void refreshAll()}
                actions={qualityActions.knowledge}
              />
            </ScreenSection>
          ) : null}
          {channels ? (
            <ScreenSection id="agente-canales" title={t("builder.screen.channels")}>
              <AgentChannelsPanel
                refId={refId}
                agentId={draft.agent_id}
                channels={channels.data}
                pages={channels.pages}
                canWrite={channels.canWrite}
                fromPhone={channels.fromPhone}
                actions={qualityActions.channels}
              />
            </ScreenSection>
          ) : null}
          {connectors ? (
            <ScreenSection id="agente-conectores" title={t("agentConn.title")}>
              <AgentConnectorsPanel
                refId={refId}
                agentId={draft.agent_id}
                connectors={connectors.data}
                canWrite={connectors.canWrite}
                spec={spec}
                actions={qualityActions.connectors}
              />
            </ScreenSection>
          ) : null}
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
          {performance ? (
            <ScreenSection id="agente-rendimiento" title={t("improve.performance.title")}>
              <AgentPerformancePanel
                refId={refId}
                agentId={draft.agent_id}
                performance={performance.performance}
                conversations={performance.conversations}
                actions={qualityActions.performance}
              />
            </ScreenSection>
          ) : null}
          {improvements ? (
            <ScreenSection id="agente-mejoras" title={t("improve.title")}>
              <AgentImprovementsPanel
                refId={refId}
                agentId={draft.agent_id}
                improvements={improvements.data}
                onAccepted={() => void refreshAll()}
                actions={qualityActions.improvements}
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
                  actions={qualityActions.review}
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
          {advanced || modelQuality ? (
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
              {modelQuality ? (
                // Agente › Avanzado › Calidad (39.4): `?tab=quality` llega aquí.
                <section id="agente-calidad" aria-labelledby="agente-calidad-title" className="grid min-w-0 scroll-mt-24 gap-3 border-t border-border pt-4 first:border-t-0 first:pt-0">
                  <h4 id="agente-calidad-title" className="text-sm font-semibold">
                    {t("modelQuality.title")}
                  </h4>
                  <AgentModelQuality
                    refId={refId}
                    agentId={draft.agent_id}
                    quality={modelQuality.data}
                    canWrite={modelQuality.canWrite && writable}
                    drafted={draftPolicy(spec)}
                    onUse={spec && writable ? saveModelPolicy : undefined}
                    actions={qualityActions.modelQuality}
                    wait={qualityActions.wait}
                  />
                </section>
              ) : null}
            </ScreenSection>
          ) : null}
        </div>
        <aside className="grid min-w-0 gap-4">
          {quality ? (
            <div className="min-w-0 rounded-md border border-border bg-card p-4">
              <AgentPlayground
                refId={refId}
                agentId={draft.agent_id}
                sessions={quality.sessions}
                versions={versions}
                hasDraft={draft.exists}
                canWrite={writable}
                onWhy={(turn) =>
                  askWhy(
                    { answer: turn.bubbles.join("\n"), actions: turn.actions },
                    t("builder.copilot.about.answer", { answer: excerpt(turn.bubbles.join(" ")) }),
                  )
                }
                actions={qualityActions.playground}
              />
            </div>
          ) : null}
          {quality && spec ? (
            <div id="agente-copiloto" className="min-w-0 scroll-mt-24 rounded-md border border-border bg-card p-4">
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
            <div id="agente-propuestas" className="min-w-0 scroll-mt-24 rounded-md border border-border bg-card p-4">
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
        </aside>
      </div>
    </div>
  );
}

/** Las primeras palabras de una respuesta, para decir de cuál se pregunta. */
function excerpt(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** Una parte de la pantalla del agente con su título (h3) y su ancla. */
function ScreenSection({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="grid min-w-0 scroll-mt-24 gap-3 rounded-md border border-border bg-card p-4 sm:p-6">
      <h3 id={`${id}-title`} className="text-base font-semibold">
        {title}
      </h3>
      {children}
    </section>
  );
}

function BlockCard({
  refId,
  block,
  spec,
  editing,
  canEdit,
  onEdit,
  children,
}: {
  refId: string;
  block: AgentBlockKey;
  spec: AgentSpec;
  editing: boolean;
  canEdit: boolean;
  onEdit: () => void;
  children: React.ReactNode;
}) {
  const t = useT();
  const titleId = React.useId();
  const title = t(blockTitleKey(block));
  const editRef = React.useRef<HTMLButtonElement>(null);
  const wasEditing = React.useRef(editing);
  // Al cerrar el editor (guardado o cancelado), el foco vuelve a «Editar».
  React.useEffect(() => {
    if (wasEditing.current && !editing) editRef.current?.focus();
    wasEditing.current = editing;
  }, [editing]);
  return (
    <li className="min-w-0">
      <section
        id={`bloque-${block}`}
        aria-labelledby={titleId}
        className="grid min-w-0 scroll-mt-24 gap-3 rounded-md border border-border bg-card p-4 sm:p-6"
        data-block={block}
      >
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <h3 id={titleId} className="text-base font-semibold text-balance">
            {title}
          </h3>
          {canEdit && !editing ? (
            <Button ref={editRef} size="sm" variant="ghost" onClick={onEdit} aria-label={t("builder.edit.label", { block: title })}>
              <Pencil aria-hidden="true" />
              {t("builder.edit")}
            </Button>
          ) : null}
        </div>
        {editing ? children : <BlockValue block={blockFromSpec(spec, block)} refId={refId} />}
      </section>
    </li>
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
