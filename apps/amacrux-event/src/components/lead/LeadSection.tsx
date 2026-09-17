"use client";

import { Button } from "@/components/ui/Button";
import { ArrowLeftIcon } from "@/components/ui/icons";
import type { PartialAnswers, Result } from "@/domain/types";
import type { DeliveryOutcome, LeadRepository } from "@/lib/leads/repository";

import { LeadForm } from "./LeadForm";

export interface LeadSectionProps {
  result: Result;
  answers: PartialAnswers;
  campaign?: string;
  repository?: LeadRepository;
  onSubmitted: (outcome: DeliveryOutcome) => void;
  onBack: () => void;
}

/** Puerta al resultado: el formulario de contacto va antes del diagnóstico (flujo v2). */
export function LeadSection({ result, answers, campaign, repository, onSubmitted, onBack }: LeadSectionProps) {
  return (
    <div className="fade-up">
      <Button variant="ghost" onClick={onBack} className="-ml-3 mb-2">
        <ArrowLeftIcon />
        Revisar mis respuestas
      </Button>
      <LeadForm result={result} answers={answers} campaign={campaign} repository={repository} onSubmitted={onSubmitted} />
    </div>
  );
}
