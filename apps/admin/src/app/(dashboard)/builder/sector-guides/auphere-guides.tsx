import { ChevronRight } from "lucide-react";

import { EmptyState, StatusBadge } from "@nexus/ui";
import type { SectorGuide } from "@/lib/backend-sector-guides";

import { DATE } from "../labels";
import { GuideView } from "./guide-view";
import { whoLabel } from "./sector-guides";

/**
 * Spec 047 (58.1, 58.5): Auphere's guides — the ones from the vertical
 * templates, in the order of the sectors, then the ones converted from a
 * generated guide, by date. Each one opens to what it says.
 */
export function AuphereGuides({ guides }: { guides: SectorGuide[] }) {
  if (!guides.length) {
    return (
      <EmptyState
        readonly
        title="No hay guías de Auphere"
        description="Las seis de las plantillas salen de la API. Si no aparece ninguna, la API no las está sirviendo."
      />
    );
  }
  return (
    <ol aria-label="Guías de Auphere" className="flex flex-col divide-y divide-border rounded-md ring-1 ring-foreground/10">
      {guides.map((g) => (
        <li key={g.key} className="min-w-0">
          <GuideRow guide={g} />
        </li>
      ))}
    </ol>
  );
}

function GuideRow({ guide: g }: { guide: SectorGuide }) {
  const origin =
    g.source === "template"
      ? g.templates.length
        ? `Sale de la plantilla ${g.templates.join(", ")}.`
        : "Sale de una plantilla."
      : `Convertida por ${whoLabel(g.published_by)}${g.published_at ? ` el ${DATE.format(new Date(g.published_at))}` : ""}.`;
  return (
    <details className="group">
      <summary className="flex min-h-12 cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="font-medium break-words">{g.label}</span> <code className="text-xs text-muted-foreground break-all">{g.key}</code>
        </span>
        <StatusBadge tone={g.source === "template" ? "muted" : "info"}>{g.source === "template" ? "Plantilla" : "Convertida"}</StatusBadge>
        {g.tests ? (
          <span className="text-xs text-muted-foreground tabular-nums">
            versión {g.version} · {g.tests === 1 ? "1 prueba" : `${g.tests} pruebas`}
          </span>
        ) : (
          <StatusBadge tone="warning">Sin pruebas</StatusBadge>
        )}
      </summary>
      <div className="flex flex-col gap-4 border-t border-border px-4 py-4">
        <p className="text-xs text-muted-foreground text-pretty">{origin}</p>
        <GuideView guide={g.guide} headingLevel={4} />
      </div>
    </details>
  );
}
