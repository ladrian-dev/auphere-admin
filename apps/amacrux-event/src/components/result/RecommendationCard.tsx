"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { ChevronDownIcon } from "@/components/ui/icons";
import { CATEGORY_LABELS, COMPLEXITY_LABELS, CONFIDENCE_LABELS, TECH_COMPLEXITY_LABELS } from "@/domain/copy";
import type { Recommendation } from "@/domain/types";
import { cx } from "@/lib/cx";

export function RecommendationCard({ rec, index, onExpand }: { rec: Recommendation; index: number; onExpand?: () => void }) {
  const [open, setOpen] = useState(index === 0);
  const o = rec.opportunity;
  const tone = rec.confidence === "prioritario" ? "accent" : rec.confidence === "relevante" ? "navy" : "neutral";
  const panelId = `rec-${o.id}`;
  return (
    <article data-testid="recommendation-card" className="rounded-lg border border-line bg-surface shadow-1 fade-up">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) onExpand?.();
        }}
        className="flex w-full items-start gap-3 p-4 text-left"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary font-display text-base font-bold text-primary-contrast" aria-hidden>
          {index + 1}
        </span>
        <span className="min-w-0 flex-1">
          <span className="mb-1.5 flex flex-wrap gap-1.5">
            <Badge tone={tone}>{CONFIDENCE_LABELS[rec.confidence]}</Badge>
            <Badge>{CATEGORY_LABELS[o.category]}</Badge>
          </span>
          <span className="block font-display text-lg font-semibold leading-snug text-ink">{o.title}</span>
          <span className="mt-1 block text-sm text-ink-muted">{rec.reasons[0]}</span>
        </span>
        <ChevronDownIcon className={cx("mt-1 shrink-0 text-ink-muted transition-transform duration-(--duration-fast)", open && "rotate-180")} />
      </button>
      <div id={panelId} hidden={!open} className="border-t border-line px-4 pb-5 pt-4 text-sm leading-relaxed text-ink">
        <dl className="grid gap-4">
          <Row label="Qué ocurre hoy">{o.problemSolved}</Row>
          <Row label="Cómo podría funcionar">{o.howItWorks}</Row>
          <Row label="Beneficio potencial">{o.benefitDescription}</Row>
          <div className="grid grid-cols-2 gap-3">
            <Row label="Complejidad">
              {COMPLEXITY_LABELS[o.complexityLabel]} · técnica {TECH_COMPLEXITY_LABELS[o.technicalComplexity].toLowerCase()}
            </Row>
            <Row label="Primer piloto">{o.expectedTimeToPilot}</Row>
          </div>
          <Row label="Podría conectar con">{o.relatedTools.join(" · ")}</Row>
          <Row label="Qué haría falta validar">
            <ul className="list-disc pl-5">
              {o.requiredInputs.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </Row>
          <Row label="Primer paso recomendado">
            <strong className="font-semibold">{o.recommendedFirstStep}</strong>
          </Row>
          <Row label="Cómo podría empezar Amacrux">{o.amacruxFit}</Row>
          {rec.reasons.length > 1 ? (
            <Row label="Por qué te lo recomendamos">
              <ul className="list-disc pl-5">
                {rec.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </Row>
          ) : null}
          {rec.warnings.length > 0 ? (
            <Row label="A tener en cuenta">
              <ul className="list-disc pl-5 text-ink-muted">
                {rec.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Row>
          ) : null}
        </dl>
      </div>
    </article>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="mb-0.5 text-xs font-semibold uppercase tracking-wider text-ink-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
