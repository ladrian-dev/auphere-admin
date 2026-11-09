"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, StatusBadge, buttonVariants, formatDateTime } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { FichaLink, Proposal, ProposalDecision, ProposalOp, SpecProblem } from "@/lib/backend/builder-types";

import { fichaLink } from "./agenda-model";
import { SpecValueAt, blockTitleKey } from "./block-view";
import { blockOfPointer, blocksOfOps, previewValue, type Result } from "./builder-model";

export type DecideProposal = (body: {
  ref: string;
  agent: string;
  proposal: string;
  decision: "apply" | "reject";
}) => Promise<Result<ProposalDecision>>;

const KINDS = new Set(["agent_spec_patch", "fix", "test_add"]);
const OPS = new Set(["add", "replace", "remove"]);

type Problem = { kind: "stale" | "closed" | "expired" | "failed" } | { kind: "invalid"; problems: SpecProblem[] };

/**
 * Las propuestas abiertas del agente (spec 047, requisitos 15.2 y 15.3): lo que
 * propusieron el constructor o el copiloto, con su resumen y lo que cambia
 * operación a operación. Nada se aplica sin que una persona con permiso pulse
 * «Aplicar». Si el borrador cambió después, se rechaza como caducada; a los 15
 * minutos caduca sola. Quien solo lee las ve, sin botones (§V).
 *
 * Spec 057 (3.3 y 3.7): lo que cambia va por bloque y, si la API manda lo que hay
 * ahora en cada puntero (`before`), con lo de antes y lo de después. «Editar»
 * (con `onEdit`) aplica la propuesta y abre el primer bloque cambiado, para
 * ajustarlo antes de publicar. Si la ficha dice que el equipo confirma las citas
 * (`diff.ficha_links`), se señala con un enlace a Negocio: la ficha es de todos
 * los agentes del cliente y la propuesta no la toca. La propuesta de la agenda
 * vive 7 días: cada una dice cuándo caduca.
 */
export function ProposalList({
  refId,
  agentId,
  proposals,
  canWrite,
  decide,
  onApplied,
  onRetry,
  onEdit,
  bare = false,
}: {
  refId: string;
  agentId: string;
  /** Solo la lista, sin título: dentro de una respuesta del copiloto. */
  bare?: boolean;
  /** `null` si no se pudieron leer. */
  proposals: Proposal[] | null;
  canWrite: boolean;
  decide: DecideProposal;
  /** Una propuesta aplicada cambió el borrador: hay que leerlo otra vez. */
  onApplied: () => void;
  onRetry: () => void;
  /** «Editar»: tras aplicarla, abrir el bloque (spec 057, 3.3). Sin él, no hay «Editar». */
  onEdit?: (block: string) => void;
}) {
  const t = useT();
  const headingId = React.useId();
  const [gone, setGone] = React.useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = React.useState<string | null>(null);
  const [problems, setProblems] = React.useState<Record<string, Problem>>({});
  const open = (proposals ?? []).filter((p) => !gone.has(p.id));
  const Heading = bare ? "h3" : "h2";

  async function run(p: Proposal, decision: "apply" | "reject", edit: string | null = null) {
    setBusy(`${p.id}:${edit ? "edit" : decision}`);
    const res = await decide({ ref: refId, agent: agentId, proposal: p.id, decision });
    setBusy(null);
    if (res.ok) {
      setGone((prev) => new Set(prev).add(p.id));
      toast.success(decision === "apply" ? t("builder.proposals.applied") : t("builder.proposals.rejected"));
      if (decision === "apply") onApplied();
      if (edit) onEdit?.(edit);
      return;
    }
    const problem: Problem =
      res.code === "proposal_stale"
        ? { kind: "stale" }
        : res.code === "proposal_closed"
          ? { kind: "closed" }
          : res.code === "proposal_expired" || res.status === 410
            ? { kind: "expired" }
            : res.code === "invalid_proposal"
              ? { kind: "invalid", problems: Array.isArray(res.info?.problems) ? (res.info.problems as SpecProblem[]) : [] }
              : { kind: "failed" };
    setProblems((prev) => ({ ...prev, [p.id]: problem }));
  }

  return (
    <section aria-labelledby={headingId} className="grid min-w-0 gap-3" data-slot="builder-proposals">
      <div className={bare ? "sr-only" : "grid min-w-0 gap-1"}>
        <Heading id={headingId} className="text-base font-semibold text-balance">
          {t("builder.proposals.title")}
        </Heading>
        {!bare ? <p className="text-sm text-pretty text-muted-foreground">{t("builder.proposals.intro")}</p> : null}
      </div>
      {proposals === null ? (
        <div className="flex min-w-0 flex-wrap items-center gap-3 text-sm">
          <p className="text-muted-foreground">{t("builder.proposals.error")}</p>
          <Button size="sm" variant="outline" onClick={onRetry}>
            {t("builder.proposals.retry")}
          </Button>
        </div>
      ) : !open.length ? (
        <p className="text-sm text-muted-foreground">{t("builder.proposals.empty")}</p>
      ) : (
        <ul className="grid min-w-0 gap-3">
          {open.map((p) => (
            <ProposalCard
              key={p.id}
              refId={refId}
              proposal={p}
              canWrite={canWrite}
              busy={busy}
              problem={problems[p.id] ?? null}
              onApply={() => void run(p, "apply")}
              onReject={() => void run(p, "reject")}
              onEdit={onEdit ? (block) => void run(p, "apply", block) : undefined}
              blockHeading={bare ? "h4" : "h3"}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function ProposalCard({
  refId,
  proposal: p,
  canWrite,
  busy,
  problem,
  onApply,
  onReject,
  onEdit,
  blockHeading: BlockHeading,
}: {
  refId: string;
  blockHeading: "h3" | "h4";
  proposal: Proposal;
  canWrite: boolean;
  busy: string | null;
  problem: Problem | null;
  onApply: () => void;
  onReject: () => void;
  onEdit?: (block: string) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const titleId = React.useId();
  const ops = Array.isArray(p.diff?.ops) ? p.diff.ops : [];
  const kind = t(KINDS.has(p.kind) ? (`builder.proposals.kind.${p.kind}` as MessageKey) : "builder.proposals.kind.other");
  const author =
    p.author === "builder" || p.author === "copilot"
      ? t(`builder.proposals.author.${p.author}` as MessageKey)
      : t("builder.proposals.author.other", { who: p.author });
  // Caducada, cerrada o fuera de fecha: ya no se puede decidir.
  const decided = problem?.kind === "stale" || problem?.kind === "closed" || problem?.kind === "expired";
  // Spec 057 (3.3): por bloque; con `before`, lo de antes y lo de después.
  const groups = blocksOfOps(ops);
  const firstBlock = groups.find((g) => g.block)?.block ?? null;
  const ficha = fichaLinks(p.diff?.ficha_links);

  return (
    <li aria-labelledby={titleId} className="grid min-w-0 gap-3 rounded-md border border-border p-3" data-slot="builder-proposal">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="grid min-w-0 flex-1 basis-56 gap-1">
          <p id={titleId} className="text-sm font-medium text-pretty break-words">
            {p.summary || kind}
          </p>
          <p className="text-xs text-muted-foreground">
            {author} · {t("builder.proposals.expires", { at: formatDateTime(p.expires_at, locale) })}
          </p>
        </div>
        <StatusBadge tone="info">{kind}</StatusBadge>
      </div>
      {ops.length ? (
        <div className="grid min-w-0 gap-2">
          <p className="text-xs font-medium text-muted-foreground">{t("builder.proposals.changes")}</p>
          {groups.map((g, gi) => (
            <div
              key={g.block ?? `loose-${gi}`}
              role="group"
              aria-labelledby={`${titleId}-b${gi}`}
              className="grid min-w-0 gap-1"
              data-slot="proposal-block"
              data-block={g.block ?? undefined}
            >
              <BlockHeading id={`${titleId}-b${gi}`} className="text-sm font-medium text-balance">
                {g.block ? t(blockTitleKey(g.block)) : t("builder.proposals.kind.other")}
              </BlockHeading>
              <ul className="grid min-w-0 gap-2 text-sm">
                {g.ops.map((op, i) => (op.before !== undefined ? <BeforeAfter key={i} op={op} /> : <OpLine key={i} op={op} />))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}
      {ficha.map((link) => (
        <FichaNote key={link.section} refId={refId} section={link.section} />
      ))}
      {problem ? <ProblemNotice problem={problem} /> : null}
      {canWrite && !decided ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={onApply} loading={busy === `${p.id}:apply`} disabled={busy !== null && busy !== `${p.id}:apply`}>
            {t("builder.proposals.apply")}
          </Button>
          {onEdit && firstBlock ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onEdit(firstBlock)}
              loading={busy === `${p.id}:edit`}
              disabled={busy !== null && busy !== `${p.id}:edit`}
              aria-label={t("agenda.diff.edit.label", { block: t(blockTitleKey(firstBlock)) })}
            >
              {t("agenda.diff.edit")}
            </Button>
          ) : null}
          <Button size="sm" variant="outline" onClick={onReject} loading={busy === `${p.id}:reject`} disabled={busy !== null && busy !== `${p.id}:reject`}>
            {t("builder.proposals.reject")}
          </Button>
        </div>
      ) : null}
    </li>
  );
}

/** Una operación de una propuesta, en palabras; la usan también las Mejoras (T174). */
export function OpLine({ op }: { op: ProposalOp }) {
  const t = useT();
  const block = blockOfPointer(op.path);
  const where = block ? t(blockTitleKey(block)) : op.path;
  const verb = OPS.has(op.op) ? (`builder.proposals.op.${op.op}` as MessageKey) : "builder.proposals.op.other";
  const value = op.op === "remove" ? "" : previewValue(op.value);
  return (
    <li className="grid min-w-0 gap-1">
      <span className="text-pretty">{t(verb, { where })}</span>
      {value ? <code className="block min-w-0 rounded-sm bg-muted px-2 py-1 text-xs break-words whitespace-pre-wrap">{value}</code> : null}
    </li>
  );
}

/**
 * Spec 057 (3.3): una operación con lo que hay ahora (`before`) y lo que propone,
 * cada lado leído como su bloque (`SpecValueAt`) y entero. Lado a lado si caben.
 */
function BeforeAfter({ op }: { op: ProposalOp }) {
  const t = useT();
  const hasBefore = op.before !== null && op.before !== undefined;
  const hasAfter = op.op !== "remove" && op.value !== undefined && op.value !== null;
  return (
    <li className="@container min-w-0" data-slot="proposal-op" data-op={op.op}>
      <div className="grid min-w-0 gap-2 @md:grid-cols-2">
        <div className="grid min-w-0 content-start gap-1 rounded-md border border-border px-3 py-2" data-side="before">
          <span className="text-xs font-medium text-muted-foreground">{t("agenda.diff.before")}</span>
          {hasBefore ? <SpecValueAt path={op.path} value={op.before} /> : <span className="text-xs text-muted-foreground">{t("agenda.diff.none")}</span>}
        </div>
        <div className="grid min-w-0 content-start gap-1 rounded-md border border-border bg-muted px-3 py-2" data-side="after">
          <span className="text-xs font-medium text-muted-foreground">{t("agenda.diff.after")}</span>
          {hasAfter ? (
            <SpecValueAt path={op.path} value={op.value} />
          ) : (
            <span className="text-xs text-muted-foreground">{op.op === "remove" ? t("agenda.diff.removed") : t("agenda.diff.none")}</span>
          )}
        </div>
      </div>
    </li>
  );
}

/** Las secciones de la ficha que la propuesta señala, una vez cada una. */
function fichaLinks(raw: unknown): FichaLink[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  return (raw as unknown[]).flatMap((item) => {
    const section = item && typeof item === "object" ? (item as { section?: unknown }).section : null;
    if (typeof section !== "string" || !section || seen.has(section)) return [];
    seen.add(section);
    return [{ section }];
  });
}

/** Spec 057 (3.7): la ficha dice que el equipo confirma las citas. Se cambia en Negocio, no aquí. */
function FichaNote({ refId, section }: { refId: string; section: string }) {
  const t = useT();
  const link = fichaLink(refId, section);
  return (
    <div className="min-w-0" data-slot="proposal-ficha">
      <Callout
        tone="info"
        action={
          <Link href={link.href} className={buttonVariants({ size: "sm", variant: "outline" })}>
            {t("agenda.ficha.go")}
          </Link>
        }
      >
        {t("agenda.ficha.note", { section: link.label ? t(link.label) : section })}
      </Callout>
    </div>
  );
}

function ProblemNotice({ problem }: { problem: Problem }) {
  const t = useT();
  if (problem.kind === "invalid") {
    return (
      <Callout tone="danger" title={t("builder.proposals.invalid")}>
        {problem.problems.length ? (
          <ul className="grid list-disc gap-1 pl-5">
            {problem.problems.map((pr, i) => (
              <li key={i} className="break-words">
                {pr.message || pr.code}
              </li>
            ))}
          </ul>
        ) : null}
      </Callout>
    );
  }
  const key: MessageKey =
    problem.kind === "stale"
      ? "builder.proposals.stale"
      : problem.kind === "closed"
        ? "builder.proposals.closed"
        : problem.kind === "expired"
          ? "builder.proposals.expired"
          : "builder.proposals.failed";
  return <Callout tone="warning">{t(key)}</Callout>;
}
