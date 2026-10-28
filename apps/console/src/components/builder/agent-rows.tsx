"use client";

import { CircleCheck, Eye, Pencil, Plug, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, StatusBadge, buttonVariants } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AgentSpec, EditableBlock, EscalationTrigger, SpecSkill } from "@/lib/backend/builder-types";

import { AGENT_ROWS, ROW_BLOCKS, ROW_TITLE_BLOCK, editableBlocks, type AgentRow } from "./agent-proto-model";
import { AiDisclosureValue, BlockValue, blockTitleKey, connectHref, triggerText } from "./block-view";
import { blockFromSpec, connectByIntegration, integrationName, isEditable, languageName, skillName, type AgentBlockKey } from "./builder-model";

/** Lo que dice la ficha del negocio para «Qué sabe»; `null` si no se pudo leer. */
export type BusinessSummary = { services: number; locations: number; hours: boolean };

/** La fila abierta y, si lo hay, el bloque que se está editando dentro. */
export type OpenRow = { row: AgentRow; block: EditableBlock | null };

/** El título de cada parte dentro de una fila abierta. */
const PART_TITLE: Partial<Record<AgentBlockKey, MessageKey>> = {
  identity: "agentProto.part.identity",
  voice: "agentProto.part.voice",
  services: "agentProto.part.services",
  skills: "agentProto.part.skills",
};
function partTitleKey(block: AgentBlockKey): MessageKey {
  return PART_TITLE[block] ?? blockTitleKey(block);
}

/**
 * Los parámetros del agente como el prototipo aprobado (§4.2 y §12): cinco
 * filas —qué hace, cómo habla, qué sabe, qué puede hacer y cuándo pasa a una
 * persona— con su título, un resumen que se lee de un vistazo y un lápiz. El
 * lápiz abre en la misma fila los editores de sus bloques (`block-editor.tsx`),
 * uno a la vez: ningún campo del AgentSpec se queda sin editar. El aviso de IA
 * vive en «Cómo habla» y, sin decidir, lo dice con «Decidir» a la vista (la
 * puerta lo exige). «Qué sabe» abre el conocimiento propio del agente.
 */
export function AgentRows({
  refId,
  spec,
  canEdit,
  open,
  onOpen,
  onClose,
  editor,
  knowledge,
  sources,
  business,
  onConnect,
}: {
  refId: string;
  spec: AgentSpec;
  canEdit: boolean;
  open: OpenRow | null;
  onOpen: (row: AgentRow, block: EditableBlock | null) => void;
  onClose: () => void;
  /** El editor de un bloque, con sus avisos (conflicto, validador). */
  editor: (block: EditableBlock) => React.ReactNode;
  /** El panel de conocimiento propio; sin él, «Qué sabe» no se abre. */
  knowledge?: React.ReactNode;
  /** Cuántas fuentes propias tiene; `null` si no se sabe. */
  sources?: number | null;
  business?: BusinessSummary | null;
  /** Un conector que falta: la pestaña Conectores. Sin ella, la página de conectores del cliente. */
  onConnect?: (integration: string) => void;
}) {
  const t = useT();
  return (
    <section aria-label={t("agentProto.table")} className="grid min-w-0 divide-y divide-border rounded-lg border border-border bg-card" data-slot="agent-rows">
      {AGENT_ROWS.map((row) => {
        const isOpen = open?.row === row;
        const editable = canEdit ? editableBlocks(row) : [];
        const opens = editable.length > 0 || (row === "knows" && Boolean(knowledge));
        return (
          <Row
            key={row}
            row={row}
            isOpen={isOpen}
            canEdit={canEdit}
            opens={opens}
            onOpen={() => onOpen(row, editable[0] ?? null)}
            onClose={onClose}
            summary={
              <RowSummary
                row={row}
                spec={spec}
                refId={refId}
                canEdit={canEdit}
                sources={sources}
                business={business}
                onConnect={onConnect}
                onDecide={() => onOpen("speaks", "ai_disclosure")}
              />
            }
            extra={
              row === "knows" && knowledge ? (
                <section aria-labelledby="fila-knows-knowledge" className="grid min-w-0 gap-2" hidden={!isOpen} data-slot="row-knowledge">
                  <h3 id="fila-knows-knowledge" className="text-sm font-medium">
                    {t("agentProto.part.knowledge")}
                  </h3>
                  {knowledge}
                </section>
              ) : null
            }
          >
            {isOpen ? (
              <OpenParts
                row={row}
                spec={spec}
                refId={refId}
                canEdit={canEdit}
                editing={open?.block ?? null}
                onEdit={(block) => onOpen(row, block)}
                editor={editor}
                onConnect={onConnect}
              />
            ) : null}
          </Row>
        );
      })}
    </section>
  );
}

function Row({
  row,
  isOpen,
  canEdit,
  opens,
  onOpen,
  onClose,
  summary,
  extra,
  children,
}: {
  row: AgentRow;
  isOpen: boolean;
  canEdit: boolean;
  opens: boolean;
  onOpen: () => void;
  onClose: () => void;
  summary: React.ReactNode;
  extra: React.ReactNode;
  children: React.ReactNode;
}) {
  const t = useT();
  const titleId = React.useId();
  const title = t(blockTitleKey(ROW_TITLE_BLOCK[row]));
  const actionRef = React.useRef<HTMLButtonElement>(null);
  const wasOpen = React.useRef(isOpen);
  // Al cerrar la fila (guardado, cancelado o «Cerrar»), el foco vuelve a su lápiz.
  React.useEffect(() => {
    if (wasOpen.current && !isOpen) actionRef.current?.focus();
    wasOpen.current = isOpen;
  }, [isOpen]);
  const label = isOpen
    ? t("agentProto.close", { row: title })
    : canEdit
      ? t("builder.edit.label", { block: title })
      : t("agentProto.view", { row: title });
  return (
    <section
      id={`fila-${row}`}
      aria-labelledby={titleId}
      className="grid min-w-0 scroll-mt-24 grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-2 px-4 py-4 sm:grid-cols-[168px_minmax(0,1fr)_auto] sm:px-5"
      data-row={row}
      data-open={isOpen || undefined}
    >
      <h2 id={titleId} className="col-start-1 row-start-1 self-center text-sm font-medium text-balance sm:self-start">
        {title}
      </h2>
      <div className="col-span-2 grid min-w-0 gap-4 sm:col-span-1 sm:col-start-2 sm:row-start-1">
        {isOpen && children ? children : summary}
        {extra}
      </div>
      {opens ? (
        <Button
          ref={actionRef}
          size="icon-sm"
          variant="ghost"
          onClick={isOpen ? onClose : onOpen}
          aria-label={label}
          aria-expanded={isOpen}
          className="col-start-2 row-start-1 justify-self-end sm:col-start-3"
        >
          {isOpen ? <X aria-hidden="true" /> : canEdit ? <Pencil aria-hidden="true" /> : <Eye aria-hidden="true" />}
        </Button>
      ) : null}
    </section>
  );
}

/** La fila abierta: cada bloque con su título, su valor y su lápiz; el que se edita, con su editor. */
function OpenParts({
  row,
  spec,
  refId,
  canEdit,
  editing,
  onEdit,
  editor,
  onConnect,
}: {
  row: AgentRow;
  spec: AgentSpec;
  refId: string;
  canEdit: boolean;
  editing: EditableBlock | null;
  onEdit: (block: EditableBlock) => void;
  editor: (block: EditableBlock) => React.ReactNode;
  onConnect?: (integration: string) => void;
}) {
  const t = useT();
  const blocks = ROW_BLOCKS[row];
  // Una fila de un solo bloque abre directamente su editor, como el prototipo.
  if (blocks.length === 1 && editing === blocks[0]) {
    return (
      <div id={`bloque-${editing}`} className="min-w-0 scroll-mt-24" data-block={editing}>
        {editor(editing)}
      </div>
    );
  }
  return (
    <>
      {blocks.map((block) => {
        const editable = canEdit && isEditable(block);
        const part = t(partTitleKey(block));
        return (
          <section
            key={block}
            id={`bloque-${block}`}
            aria-labelledby={`bloque-${block}-title`}
            className="grid min-w-0 scroll-mt-24 gap-2 border-t border-border pt-4 first:border-t-0 first:pt-0"
            data-block={block}
          >
            <div className="flex min-w-0 items-center justify-between gap-2">
              <h3 id={`bloque-${block}-title`} className="text-sm font-medium text-muted-foreground">
                {part}
              </h3>
              {editable && editing !== block ? (
                <Button size="icon-sm" variant="ghost" onClick={() => onEdit(block as EditableBlock)} aria-label={t("builder.edit.label", { block: part })}>
                  <Pencil aria-hidden="true" />
                </Button>
              ) : null}
            </div>
            {editing === block ? (
              editor(block)
            ) : block === "ai_disclosure" ? (
              <AiDisclosureValue value={spec.ai_disclosure} />
            ) : block === "skills" ? (
              <SkillLines spec={spec} refId={refId} onConnect={onConnect} />
            ) : (
              <BlockValue block={blockFromSpec(spec, block)} refId={refId} />
            )}
          </section>
        );
      })}
    </>
  );
}

// ── lo que dice cada fila cerrada ───────────────────────────────────────────

function RowSummary({
  row,
  spec,
  refId,
  canEdit,
  sources,
  business,
  onConnect,
  onDecide,
}: {
  row: AgentRow;
  spec: AgentSpec;
  refId: string;
  canEdit: boolean;
  sources?: number | null;
  business?: BusinessSummary | null;
  onConnect?: (integration: string) => void;
  onDecide: () => void;
}) {
  switch (row) {
    case "does":
      return <DoesSummary spec={spec} refId={refId} />;
    case "speaks":
      return <SpeaksSummary spec={spec} canEdit={canEdit} onDecide={onDecide} />;
    case "knows":
      return <KnowsSummary spec={spec} sources={sources} business={business} />;
    case "can":
      return <CanSummary spec={spec} refId={refId} onConnect={onConnect} />;
    case "handoff":
      return <HandoffSummary spec={spec} />;
  }
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-pretty text-muted-foreground">{children}</p>;
}

function DoesSummary({ spec, refId }: { spec: AgentSpec; refId: string }) {
  const t = useT();
  const sections = spec.instructions?.sections?.length ?? 0;
  const legacy = !sections && spec.instructions?.legacy_text !== undefined;
  const rules = spec.rules?.length ?? 0;
  const counts = [
    legacy ? t("agentProto.does.legacy") : sections === 1 ? t("agentProto.does.sections.one") : t("agentProto.does.sections.other", { n: sections }),
    rules === 1 ? t("agentProto.does.rules.one") : t("agentProto.does.rules.other", { n: rules }),
  ].join(" · ");
  return (
    <div className="grid min-w-0 gap-2 text-sm">
      <p className="text-pretty break-words">{spec.identity.description}</p>
      {spec.identity.goal ? <p className="text-pretty break-words text-muted-foreground">{t("builder.block.goal", { goal: spec.identity.goal })}</p> : null}
      <Note>{counts}</Note>
      {sections || legacy || rules ? (
        <details className="group min-w-0">
          <summary className="w-fit cursor-pointer list-none text-xs font-medium text-primary-text underline underline-offset-4 hover:no-underline [&::-webkit-details-marker]:hidden">
            {t("agentProto.does.more")}
          </summary>
          <div className="mt-2 grid min-w-0 gap-4">
            <BlockValue block={blockFromSpec(spec, "instructions")} refId={refId} />
            {rules ? <BlockValue block={blockFromSpec(spec, "rules")} refId={refId} /> : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}

/** «Cercano, de tú. Saluda: «¡Hola!…».» */
function voiceSentence(voice: AgentSpec["voice"], t: ReturnType<typeof useT>): string | null {
  const parts: string[] = [];
  const tone = voice?.tone?.trim().replace(/[.\s]+$/, "");
  if (tone) parts.push(tone);
  if (voice?.register) parts.push(t(`agentProto.speaks.register.${voice.register}` as MessageKey));
  let out = parts.join(", ");
  if (out) out = `${out.charAt(0).toUpperCase()}${out.slice(1)}.`;
  if (voice?.greeting) out = `${out ? `${out} ` : ""}${t("agentProto.speaks.greets", { greeting: voice.greeting.trim() })}`;
  return out || null;
}

function SpeaksSummary({ spec, canEdit, onDecide }: { spec: AgentSpec; canEdit: boolean; onDecide: () => void }) {
  const t = useT();
  const locale = useLocale();
  const sentence = voiceSentence(spec.voice, t);
  const languages = spec.voice?.languages ?? [];
  const ai = spec.ai_disclosure;
  return (
    <div className="grid min-w-0 gap-2 text-sm">
      <p className={`text-pretty break-words ${sentence ? "" : "text-muted-foreground"}`}>{sentence ?? t("builder.block.voice.empty")}</p>
      {languages.length > 1 ? <Note>{t("agentProto.speaks.languages", { list: languages.map((c) => languageName(c, locale)).join(", ") })}</Note> : null}
      {ai?.decided ? (
        <Note>{t(`agentProto.speaks.ai.${ai.mode ?? "none"}` as MessageKey)}</Note>
      ) : (
        <div className="flex min-w-0 flex-wrap items-center gap-2" data-slot="ai-undecided">
          <StatusBadge tone="warn">{t("agentProto.speaks.ai.undecided")}</StatusBadge>
          {canEdit ? (
            <button
              type="button"
              onClick={onDecide}
              aria-label={t("agentProto.speaks.ai.decide.label")}
              className="cursor-pointer text-xs font-medium text-primary-text underline underline-offset-4 hover:no-underline"
            >
              {t("agentProto.speaks.ai.decide")}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}

function KnowsSummary({ spec, sources, business }: { spec: AgentSpec; sources?: number | null; business?: BusinessSummary | null }) {
  const t = useT();
  const services = spec.services;
  const listed = services?.mode === "list" ? (services.service_ids?.length ?? 0) : null;
  const faqs = services?.faqs?.length ?? 0;
  let line: string;
  if (business) {
    const parts: string[] = [];
    if (listed !== null) parts.push(t("agentProto.knows.services.some", { k: listed, n: business.services }));
    else if (business.services) parts.push(business.services === 1 ? t("agentProto.knows.services.one") : t("agentProto.knows.services.other", { n: business.services }));
    if (business.locations) parts.push(business.locations === 1 ? t("agentProto.knows.locations.one") : t("agentProto.knows.locations.other", { n: business.locations }));
    if (business.hours) parts.push(t("agentProto.knows.hours"));
    line = parts.length
      ? t("agentProto.knows.fromRecord", { parts: parts.join(" · ") })
      : listed !== null
        ? t("builder.block.services.list", { n: listed })
        : t("builder.block.services.all");
  } else {
    line = listed !== null ? t("builder.block.services.list", { n: listed }) : t("builder.block.services.all");
  }
  const own: string[] = [];
  if (faqs) own.push(t("builder.block.services.faqs", { n: faqs }));
  if (sources) own.push(sources === 1 ? t("agentProto.knows.sources.one") : t("agentProto.knows.sources.other", { n: sources }));
  return (
    <div className="grid min-w-0 gap-2 text-sm">
      <p className="text-pretty break-words">{line}</p>
      {own.length ? <Note>{own.join(" · ")}</Note> : null}
      <Note>{t("agentProto.knows.note")}</Note>
    </div>
  );
}

function CanSummary({ spec, refId, onConnect }: { spec: AgentSpec; refId: string; onConnect?: (integration: string) => void }) {
  const t = useT();
  const procedures = spec.procedures ?? [];
  return (
    <div className="grid min-w-0 gap-2 text-sm">
      <SkillLines spec={spec} refId={refId} onConnect={onConnect} />
      {procedures.length ? (
        <ul className="grid min-w-0 gap-1" data-slot="row-procedures">
          {procedures.map((p) => (
            <li key={p.id} className="text-pretty break-words text-muted-foreground">
              {t("agentProto.can.procedure", { title: p.title, when: p.when })}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Una línea por habilidad, como el prototipo (§4.4): su nombre y, a la
 * derecha, «{conector} · conectado» o «Conectar {conector}». Apagada, lo dice;
 * sin su conector, lo que hace mientras tanto. Lo que se pide conectar sin una
 * habilidad que lo nombre va en su propia línea.
 */
function SkillLines({ spec, refId, onConnect }: { spec: AgentSpec; refId: string; onConnect?: (integration: string) => void }) {
  const t = useT();
  const skills: SpecSkill[] = Array.isArray(spec.skills) ? spec.skills : [];
  const missing = connectByIntegration(spec.connection_requests);
  const named = new Set(skills.map((s) => s.integration).filter((i): i is string => Boolean(i)));
  const loose = [...missing.keys()].filter((integration) => !named.has(integration));
  if (!skills.length && !loose.length) return <p className="text-pretty text-muted-foreground">{t("agentProto.can.none")}</p>;
  return (
    <ul className="grid min-w-0 gap-2" data-slot="builder-skills">
      {skills.map((s) => {
        const needs = s.integration && missing.has(s.integration) ? s.integration : null;
        return (
          <SkillLine
            key={s.key}
            name={skillName(s.key)}
            off={!s.enabled}
            fallback={needs ? s.fallback : undefined}
            needs={needs}
            connected={s.integration && !needs ? s.integration : null}
            refId={refId}
            onConnect={onConnect}
          />
        );
      })}
      {loose.map((integration) => (
        <SkillLine key={`connect-${integration}`} name={integrationName(integration)} needs={integration} connected={null} refId={refId} onConnect={onConnect} />
      ))}
    </ul>
  );
}

function SkillLine({
  name,
  off,
  fallback,
  needs,
  connected,
  refId,
  onConnect,
}: {
  name: string;
  off?: boolean;
  fallback?: string;
  needs: string | null;
  connected: string | null;
  refId: string;
  onConnect?: (integration: string) => void;
}) {
  const t = useT();
  return (
    <li className="flex min-w-0 flex-wrap items-center justify-between gap-x-2 gap-y-1" data-slot="builder-skill">
      <span className="grid min-w-0 flex-1 basis-40 gap-1">
        <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
          <span className="break-words">{name}</span>
          {off ? <StatusBadge tone="muted">{t("builder.block.skills.off")}</StatusBadge> : null}
        </span>
        {fallback ? <span className="text-xs text-pretty text-muted-foreground">{t("builder.block.skills.fallback", { text: fallback })}</span> : null}
      </span>
      {needs ? (
        onConnect ? (
          <Button size="sm" variant="outline" className="shrink-0" onClick={() => onConnect(needs)}>
            <Plug aria-hidden="true" />
            {t("builder.connect", { name: integrationName(needs) })}
          </Button>
        ) : (
          <Link href={connectHref(refId)} className={buttonVariants({ size: "sm", variant: "outline", className: "shrink-0" })}>
            <Plug aria-hidden="true" />
            {t("builder.connect", { name: integrationName(needs) })}
          </Link>
        )
      ) : connected ? (
        <StatusBadge tone="positive" dot={false}>
          <span className="inline-flex items-center gap-1">
            <CircleCheck aria-hidden="true" className="size-3 text-status-positive-text" />
            {t("agentProto.can.connected", { name: integrationName(connected) })}
          </span>
        </StatusBadge>
      ) : null}
    </li>
  );
}

function HandoffSummary({ spec }: { spec: AgentSpec }) {
  const t = useT();
  const triggers: EscalationTrigger[] = Array.isArray(spec.escalation?.triggers) ? spec.escalation.triggers : [];
  const attempts = spec.escalation?.failed_attempts ?? 2;
  return (
    <div className="grid min-w-0 gap-2 text-sm">
      {triggers.length ? (
        <ul className="grid min-w-0 gap-1">
          {triggers.map((tr, i) => (
            <li key={i} className="text-pretty break-words">
              {triggerText(tr, attempts, t)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-pretty text-muted-foreground">{t("builder.block.escalation.empty")}</p>
      )}
      {spec.escalation?.message ? <p className="text-pretty break-words text-muted-foreground">{t("builder.block.escalation.message", { message: spec.escalation.message })}</p> : null}
      <Note>{t("agentProto.handoff.note")}</Note>
    </div>
  );
}
