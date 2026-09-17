"use client";

import { useEffect, useState } from "react";

import { BrandIsotipo } from "@/components/ui/BrandMark";

const MESSAGES = ["Analizando tus respuestas…", "Comparando con el catálogo de oportunidades…", "Priorizando lo que más encaja contigo…"];

export function ProcessingScreen() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setI((x) => (x + 1) % MESSAGES.length), 600);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div role="status" aria-live="polite" className="flex min-h-[50vh] flex-col items-center justify-center gap-6 text-center fade-up">
      <div className="relative">
        <span className="absolute inset-0 animate-ping rounded-full bg-accent/40" aria-hidden />
        <BrandIsotipo size={72} className="relative" />
      </div>
      <p className="font-display text-xl font-semibold text-ink">{MESSAGES[i]}</p>
      <p className="max-w-sm text-sm text-ink-muted">Todo se calcula en tu dispositivo. No enviamos tus respuestas a ningún sitio.</p>
    </div>
  );
}
