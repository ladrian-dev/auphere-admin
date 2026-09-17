"use client";

import { Suspense } from "react";

import { Button } from "@/components/ui/Button";
import { ArrowRightIcon } from "@/components/ui/icons";
import { TOTAL_QUESTIONS } from "@/domain/questions";
import { track } from "@/lib/analytics";
import { readCampaign } from "@/lib/campaign";

import { CampaignCapture } from "./CampaignCapture";

/** Bienvenida: cabe en la pantalla del celular sin scroll (incluido el pie). */
export function Welcome({ slug }: { slug?: string }) {
  return (
    <div className="flex h-full flex-1 flex-col items-center justify-center py-6 text-center fade-up">
      <Suspense fallback={null}>
        <CampaignCapture slug={slug} />
      </Suspense>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Diagnóstico IA</p>
      <h1 className="mt-3 max-w-md font-display text-[2.1rem] font-bold leading-[1.08] text-ink-on-strong sm:text-5xl">
        Descubre dónde la IA puede ayudar a tu empresa
      </h1>
      <div className="mt-8 w-full max-w-sm">
        <Button
          variant="accent"
          size="lg"
          full
          onClick={() => {
            track("assessment_started", { campaign: readCampaign() });
            window.location.assign("/diagnostico");
          }}
        >
          Empezar diagnóstico
          <ArrowRightIcon />
        </Button>
        <p className="mt-3 text-sm text-ink-on-strong/75">{TOTAL_QUESTIONS} preguntas rápidas y 3 recomendaciones prácticas para tu negocio.</p>
      </div>
    </div>
  );
}
