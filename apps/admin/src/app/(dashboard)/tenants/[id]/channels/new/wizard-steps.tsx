"use client";

import { Check } from "lucide-react";
import { usePathname } from "next/navigation";

import { cn } from "@nexus/ui";

const STEPS = [
  { title: "Elegir canal", body: "Por dónde escribirán los clientes de este negocio." },
  { title: "Conectar", body: "Autoriza la cuenta del proveedor y crea el canal." },
  { title: "Asignar agente", body: "Qué agente del cliente atiende este canal." },
  { title: "¡Listo!", body: "El agente ya responde por aquí." },
];

/** Which step a wizard path is on: /new · /new/{c} · /new/{c}/agent · /new/{c}/done. */
export function stepOf(pathname: string): number {
  const rest = pathname.split("/channels/new")[1] ?? "";
  const parts = rest.split("/").filter(Boolean);
  if (parts.length === 0) return 0;
  if (parts[1] === "agent") return 2;
  if (parts[1] === "done") return 3;
  return 1;
}

/** Spec 035: Chatwoot's wizard rail — numbered steps, done ones checked. */
export function WizardSteps({ compact = false }: { compact?: boolean }) {
  const current = stepOf(usePathname());
  if (compact) {
    return (
      <ol className="flex flex-wrap items-center gap-x-6 gap-y-2" aria-label="Pasos">
        {STEPS.map((s, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li key={s.title} className="flex items-center gap-2" aria-current={active ? "step" : undefined}>
              <span
                className={cn(
                  "grid size-6 shrink-0 place-items-center rounded-full text-xs font-medium tabular-nums",
                  done ? "bg-primary text-primary-foreground" : active ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground",
                )}
              >
                {done ? <Check className="size-3" aria-hidden="true" /> : i + 1}
              </span>
              <span className={cn("text-sm", active ? "font-medium text-primary-text" : "text-muted-foreground")}>{s.title}</span>
            </li>
          );
        })}
      </ol>
    );
  }
  return (
    <ol className="flex flex-col gap-6" aria-label="Pasos">
      {STEPS.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s.title} className="flex gap-3" aria-current={active ? "step" : undefined}>
            <span
              className={cn(
                "grid size-8 shrink-0 place-items-center rounded-full text-sm font-medium tabular-nums",
                done ? "bg-primary text-primary-foreground" : active ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground",
              )}
            >
              {done ? <Check className="size-4" aria-hidden="true" /> : i + 1}
            </span>
            <span className="flex flex-col gap-1">
              <span className={cn("text-sm font-medium", active ? "text-primary-text" : "")}>{s.title}</span>
              <span className="text-sm text-pretty text-muted-foreground">{s.body}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
