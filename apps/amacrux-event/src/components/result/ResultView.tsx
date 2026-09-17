"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { ArrowLeftIcon, RefreshIcon } from "@/components/ui/icons";
import type { Result } from "@/domain/types";
import { track } from "@/lib/analytics";
import { isDemoModeFlag } from "@/lib/env";

import { OpportunityLevel } from "./OpportunityLevel";
import { RecommendationCard } from "./RecommendationCard";

export interface ResultViewProps {
  result: Result;
  /** Resultado del envío del contacto: true entregado, false modo demo, undefined desconocido. */
  delivered?: boolean;
  campaign?: string;
  onBack: () => void;
  onRestart: () => void;
}

export function ResultView({ result, delivered, campaign, onBack, onRestart }: ResultViewProps) {
  useEffect(() => {
    track("result_viewed", {
      profileCategory: result.segment.profile,
      maturityLevel: result.segment.maturity,
      intentLevel: result.segment.intent,
      recommendationCategory: result.recommendations[0].opportunity.category,
      campaign,
    });
  }, [result, campaign]);

  const demo = delivered === false || (delivered === undefined && isDemoModeFlag());

  return (
    <div className="fade-up">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-accent-deep">Resultado</p>
      <h1 className="mb-2 font-display text-3xl font-bold text-ink">Tu diagnóstico</h1>
      <p className="mb-5 text-sm text-ink-muted">
        {result.summary.profileLabel} · {result.summary.sectorLabel} · {result.summary.maturityLabel}
      </p>

      <OpportunityLevel level={result.summary.opportunityLevel} />

      <p className="mt-6 text-base leading-relaxed text-ink">{result.intro}</p>

      <h2 className="mb-3 mt-8 font-display text-xl font-semibold text-ink">Tres oportunidades prioritarias</h2>
      <div className="flex flex-col gap-3">
        {result.recommendations.map((rec, i) => (
          <RecommendationCard key={rec.opportunity.id} rec={rec} index={i} onExpand={() => track("recommendation_selected", { recommendationCategory: rec.opportunity.category, campaign })} />
        ))}
      </div>

      <h2 className="mb-3 mt-8 font-display text-xl font-semibold text-ink">Cómo empezar</h2>
      <div className="grid gap-3">
        <Callout tone="success" title="A corto plazo">
          {result.shortTerm}
        </Callout>
        <Callout tone="info" title="A medio plazo">
          {result.midTerm}
        </Callout>
        {result.warnings.length > 0 ? (
          <Callout tone="warning" title="Antes de empezar, conviene validar">
            <ul className="list-disc pl-4">
              {result.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </Callout>
        ) : null}
      </div>

      <div className="mt-8 rounded-lg bg-surface-strong p-5 text-ink-on-strong shadow-3">
        <h2 className="font-display text-xl font-semibold">Siguiente paso: una DEMO con Amacrux</h2>
        <p className="mt-1 text-sm text-ink-on-strong/80">
          {demo
            ? "Modo demostración: tu contacto se ha registrado sin enviar correo. Con la entrega activa, Amacrux recibe este diagnóstico al instante."
            : "Ya tenemos tu contacto. Amacrux te escribirá en los próximos días para definir una DEMO sobre la primera oportunidad."}
          {/* TODO_COMERCIAL: validar con Amacrux el plazo de respuesta prometido. */}
        </p>
      </div>

      <div className="mt-6 flex flex-col gap-2 sm:flex-row">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeftIcon />
          Revisar mis respuestas
        </Button>
        <Button variant="ghost" onClick={onRestart}>
          <RefreshIcon />
          Reiniciar el diagnóstico
        </Button>
      </div>
      <p className="mt-6 text-xs text-ink-muted">Las recomendaciones son orientativas: requieren validar datos, volumen y sistemas actuales.</p>
    </div>
  );
}
