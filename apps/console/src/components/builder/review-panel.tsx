"use client";

import { Check, TriangleAlert } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, StatusBadge, buttonVariants } from "@nexus/ui";

import { decideProposalAction } from "@/app/(console)/clients/[ref]/agents/builder-actions";
import { reviewAction } from "@/app/(console)/clients/[ref]/agents/quality-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { AgentReview, ReviewCheck, ReviewFinding } from "@/lib/backend/agent-quality-types";

import type { Result } from "./builder-model";
import type { DecideProposal } from "./proposals";
import { reviewFixLink } from "./quality-model";

export type ReviewActions = {
  load: (body: { ref: string; agent: string }) => Promise<Result<AgentReview>>;
  decide: DecideProposal;
};

const SERVER_ACTIONS: ReviewActions = {
  load: (body) => reviewAction(body),
  decide: (body) => decideProposalAction(body),
};

const CHECKS = new Set([
  "skills_integrations",
  "services",
  "hours",
  "contradictions",
  "promises",
  "tools_exist",
  "escalation_recipients",
  "ai_disclosure",
]);

/**
 * La revisión automática (spec 047, historia 8; requisito 22): cada
 * comprobación con su resultado de verdad —nada de «✓» fijos (22.3)— y cada
 * hallazgo con su gravedad («Bloquea» o «Avisa») y su arreglo en un clic
 * cuando lo hay (22.2): ir a Conectores, a Servicios, a Horario o al canal;
 * abrir el bloque del borrador; o aplicar la propuesta que trae.
 *
 * Se lee al abrir la pantalla y cada vez que cambia el borrador. Quien solo lee
 * ve los hallazgos y sus enlaces, pero no aplica nada.
 */
export function ReviewPanel({
  refId,
  agentId,
  canWrite,
  refreshKey = 0,
  onEdit,
  onApplied,
  actions = SERVER_ACTIONS,
}: {
  refId: string;
  agentId: string;
  canWrite: boolean;
  refreshKey?: number;
  /** Un arreglo «edit»: abrir el bloque del borrador al que apunta. */
  onEdit?: (pointer: string | null) => void;
  /** Una propuesta aplicada cambió el borrador. */
  onApplied?: () => void;
  actions?: ReviewActions;
}) {
  const t = useT();
  const [review, setReview] = React.useState<AgentReview | null>(null);
  const [state, setState] = React.useState<"loading" | "ready" | "failed">("loading");
  const [applying, setApplying] = React.useState<string | null>(null);

  const fetchReview = React.useCallback(() => actions.load({ ref: refId, agent: agentId }), [actions, refId, agentId]);
  const show = React.useCallback((res: Result<AgentReview>) => {
    if (res.ok) {
      setReview(res.data);
      setState("ready");
    } else setState("failed");
  }, []);

  // Al abrir la pantalla y cada vez que cambia el borrador.
  React.useEffect(() => {
    let live = true;
    void fetchReview().then((res) => {
      if (live) show(res);
    });
    return () => {
      live = false;
    };
  }, [fetchReview, show, refreshKey]);

  async function load() {
    setState("loading");
    show(await fetchReview());
  }

  async function apply(proposalId: string) {
    setApplying(proposalId);
    const res = await actions.decide({ ref: refId, agent: agentId, proposal: proposalId, decision: "apply" });
    setApplying(null);
    if (res.ok) {
      toast.success(t("builder.review.fix.applied"));
      onApplied?.();
      return;
    }
    toast.error(t("builder.review.fix.failed"));
  }

  return (
    <div className="grid min-w-0 gap-4" data-slot="review-panel" aria-busy={state === "loading" || undefined}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 basis-56 text-sm text-pretty text-muted-foreground">{t("builder.review.intro")}</p>
        <Button size="sm" variant="outline" onClick={() => void load()} loading={state === "loading"}>
          {t("builder.review.again")}
        </Button>
      </div>
      <p role="status" className="text-sm text-muted-foreground empty:hidden">
        {state === "loading" && !review ? t("builder.review.loading") : ""}
      </p>
      {state === "failed" ? (
        <p role="alert" className="text-sm text-destructive">
          {t("builder.review.error")}
        </p>
      ) : null}
      {review ? (
        <>
          <div className="grid min-w-0 gap-2">
            <h4 className="text-sm font-semibold" id="review-checks">
              {t("builder.review.checks")}
            </h4>
            <ul aria-labelledby="review-checks" className="grid min-w-0 gap-1" data-slot="review-checks">
              {review.checks.map((check) => (
                <CheckRow key={check.check} check={check} />
              ))}
            </ul>
          </div>
          <div className="grid min-w-0 gap-2">
            <h4 className="text-sm font-semibold" id="review-findings">
              {t("builder.review.findings")}
            </h4>
            {review.findings.length ? (
              <ul aria-labelledby="review-findings" className="grid min-w-0 gap-2" data-slot="review-findings">
                {review.findings.map((finding, i) => (
                  <FindingRow
                    key={`${finding.code}-${i}`}
                    refId={refId}
                    finding={finding}
                    canWrite={canWrite}
                    applying={applying}
                    onEdit={onEdit}
                    onApply={(id) => void apply(id)}
                  />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t("builder.review.none")}</p>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

function CheckRow({ check }: { check: ReviewCheck }) {
  const t = useT();
  const label = CHECKS.has(check.check) ? t(`builder.review.check.${check.check}` as MessageKey) : check.check;
  const result = check.ok
    ? t("builder.review.ok")
    : check.findings === 1
      ? t("builder.review.found.one")
      : t("builder.review.found.other", { n: check.findings });
  return (
    <li className="flex min-w-0 items-start gap-2 text-sm" data-slot="review-check" data-ok={check.ok}>
      {check.ok ? (
        <Check aria-hidden="true" className="mt-1 size-4 shrink-0 text-status-positive-text" />
      ) : (
        <TriangleAlert aria-hidden="true" className="mt-1 size-4 shrink-0 text-warning" />
      )}
      <span className="min-w-0 flex-1 text-pretty">{label}</span>
      <span className="shrink-0 text-right text-muted-foreground">{result}</span>
    </li>
  );
}

function FindingRow({
  refId,
  finding,
  canWrite,
  applying,
  onEdit,
  onApply,
}: {
  refId: string;
  finding: ReviewFinding;
  canWrite: boolean;
  applying: string | null;
  onEdit?: (pointer: string | null) => void;
  onApply: (proposalId: string) => void;
}) {
  const t = useT();
  const fix = finding.fix;
  const link = fix?.kind === "link" ? reviewFixLink(refId, fix) : null;
  return (
    <li className="grid min-w-0 gap-2 rounded-md border border-border p-3" data-slot="review-finding" data-severity={finding.severity}>
      <div className="flex min-w-0 flex-wrap items-start gap-2">
        <StatusBadge tone={finding.severity === "block" ? "danger" : "warn"}>
          {finding.severity === "block" ? t("builder.review.block") : t("builder.review.warn")}
        </StatusBadge>
        <p className="min-w-0 flex-1 basis-48 text-sm text-pretty break-words">{finding.message}</p>
      </div>
      {link ? (
        <div>
          <Link href={link.href} className={buttonVariants({ size: "sm", variant: "outline" })}>
            {t(link.label)}
          </Link>
        </div>
      ) : null}
      {fix?.kind === "edit" && canWrite && onEdit ? (
        <div>
          <Button size="sm" variant="outline" onClick={() => onEdit(fix.pointer ?? finding.pointer ?? null)}>
            {t("builder.review.fix.edit")}
          </Button>
        </div>
      ) : null}
      {fix?.kind === "proposal" && canWrite ? (
        <div>
          <Button size="sm" onClick={() => onApply(fix.proposal_id)} loading={applying === fix.proposal_id} disabled={applying !== null && applying !== fix.proposal_id}>
            {t("builder.review.fix.apply")}
          </Button>
        </div>
      ) : null}
    </li>
  );
}
