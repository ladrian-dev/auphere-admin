"use client";

import { useState } from "react";

import { Button, DescriptionList, EmptyState, StatusBadge, cn } from "@nexus/ui";
import type { SectorCatalog, SectorTest } from "@/lib/backend-builder";

import { DATE, actorLabel } from "../labels";
import { SectorEditor } from "./sector-editor";
import { TESTS_PER_SECTOR } from "./sector-tests";

type Props = { sectors: SectorCatalog[]; operatorId: string };

/**
 * Spec 047 (T090, 21.1, 54.10): the 12 tests of each sector in the version in
 * force, and the editor that publishes a new one. While editing, the sector
 * cannot change: an edit never travels to another sector.
 */
export function SectorCatalogView({ sectors, operatorId }: Props) {
  const [selected, setSelected] = useState(sectors[0]?.sector ?? "");
  const [editing, setEditing] = useState(false);
  const current = sectors.find((s) => s.sector === selected);
  if (!current) {
    return <EmptyState readonly title="No hay sectores" description="La API no devolvió ningún sector del constructor." />;
  }
  return (
    <div className="flex flex-col gap-4">
      <nav aria-label="Sector" className="flex flex-wrap gap-1 rounded-md bg-muted p-1 text-sm sm:w-fit">
        {sectors.map((s) => (
          <button
            key={s.sector}
            type="button"
            aria-pressed={s.sector === selected}
            disabled={editing && s.sector !== selected}
            title={editing && s.sector !== selected ? "Publica o cancela la edición para cambiar de sector." : undefined}
            onClick={() => setSelected(s.sector)}
            className={cn(
              "min-h-6 rounded-sm px-3 py-1 outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
              s.sector === selected ? "bg-card font-medium shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {s.name}
          </button>
        ))}
      </nav>
      {editing ? (
        <SectorEditor key={`${current.sector}:${current.version ?? 0}`} sector={current} onDone={() => setEditing(false)} />
      ) : (
        <SectorReadView sector={current} operatorId={operatorId} onEdit={() => setEditing(true)} />
      )}
    </div>
  );
}

function SectorReadView({ sector, operatorId, onEdit }: { sector: SectorCatalog; operatorId: string; onEdit: () => void }) {
  if (sector.version === null) {
    return (
      <EmptyState
        title={`${sector.name} no tiene pruebas publicadas`}
        description={`Sin versión, los agentes nuevos de este sector nacen sin las ${TESTS_PER_SECTOR} pruebas comunes.`}
        action={<Button onClick={onEdit}>Escribir la versión 1</Button>}
      />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground text-pretty">
          En vigor la versión {sector.version} · {sector.tests.length} pruebas · publicada por{" "}
          {actorLabel(sector.published_by, operatorId)}
          {sector.published_at ? ` el ${DATE.format(new Date(sector.published_at))}` : ""}
        </p>
        <Button size="sm" variant="outline" onClick={onEdit}>
          Editar y publicar versión nueva
        </Button>
      </div>
      <ol aria-label={`Pruebas de ${sector.name}`} className="flex flex-col divide-y divide-border rounded-md ring-1 ring-foreground/10">
        {sector.tests.map((t, i) => (
          <li key={t.key}>
            <TestDetails test={t} index={i} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function TestDetails({ test, index }: { test: SectorTest; index: number }) {
  const state = test.expected_state ?? {};
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <span className="w-6 shrink-0 text-xs text-muted-foreground tabular-nums">{index + 1}</span>
        <span className="min-w-0 flex-1">
          <span className="font-medium">{test.name}</span> <code className="text-xs text-muted-foreground">{test.key}</code>
        </span>
        <span className="hidden text-xs text-muted-foreground sm:inline">
          {test.criteria.length === 1 ? "1 criterio" : `${test.criteria.length} criterios`}
        </span>
        <StatusBadge tone={test.critical ? "warning" : "muted"}>{test.critical ? "Crítica" : "Normal"}</StatusBadge>
      </summary>
      <div className="px-4 pb-4">
        <DescriptionList
          layout="inline"
          items={[
            { key: "persona", term: "Persona simulada", detail: test.persona || "—" },
            { key: "first", term: "Primer mensaje", detail: <q>{test.first_message}</q> },
            { key: "plan", term: "Plan", detail: test.plan || "—" },
            {
              key: "state",
              term: "Estado esperado",
              detail: Object.keys(state).length ? (
                <pre className="overflow-x-auto font-mono text-xs">{JSON.stringify(state, null, 2)}</pre>
              ) : (
                <span className="text-muted-foreground">Sin estado que comprobar: decide el juez.</span>
              ),
            },
            {
              key: "criteria",
              term: "Criterios",
              detail: (
                <ul className="flex flex-col gap-1">
                  {test.criteria.map((c) => (
                    <li key={c.key} className="text-pretty">
                      <code className="text-xs text-muted-foreground">{c.key}</code> {c.text}
                    </li>
                  ))}
                </ul>
              ),
            },
          ]}
        />
      </div>
    </details>
  );
}
