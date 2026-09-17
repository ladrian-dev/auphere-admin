"use client";

import { Button } from "@/components/ui/Button";
import { ArrowLeftIcon, ArrowRightIcon } from "@/components/ui/icons";

export interface StepNavProps {
  canBack: boolean;
  canNext: boolean;
  isLast: boolean;
  autoAdvances: boolean;
  onBack: () => void;
  onNext: () => void;
}

export function StepNav({ canBack, canNext, isLast, autoAdvances, onBack, onNext }: StepNavProps) {
  return (
    <div className="sticky bottom-0 -mx-4 mt-4 border-t border-line bg-canvas/95 px-4 py-2.5 backdrop-blur sm:-mx-6 sm:px-6">
      <div className="flex gap-3">
        <Button variant="secondary" size="lg" onClick={onBack} disabled={!canBack} aria-label="Atrás" className="w-14 shrink-0 px-0">
          <ArrowLeftIcon size={26} />
        </Button>
        <Button variant={autoAdvances && !canNext ? "secondary" : "accent"} onClick={onNext} disabled={!canNext} full size="lg">
          {isLast ? "Ver mi resultado" : "Continuar"}
          <ArrowRightIcon />
        </Button>
      </div>
      {autoAdvances ? <p className="mt-1.5 text-center text-[11px] text-ink-muted">Toca una opción y pasamos a la siguiente.</p> : null}
    </div>
  );
}
