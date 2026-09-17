"use client";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";

export function ErrorPanel({ message, onRetry, onRestart }: { message: string; onRetry: () => void; onRestart: () => void }) {
  return (
    <div className="fade-up">
      <Callout tone="warning" title="Algo no ha salido bien">
        {message}
      </Callout>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Button variant="accent" onClick={onRetry}>
          Reintentar
        </Button>
        <Button variant="secondary" onClick={onRestart}>
          Reiniciar el diagnóstico
        </Button>
      </div>
    </div>
  );
}
