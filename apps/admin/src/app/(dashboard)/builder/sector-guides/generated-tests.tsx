import type { ReactNode } from "react";

import { DescriptionList, StatusBadge } from "@nexus/ui";
import type { SectorTest } from "@/lib/backend-builder";
import type { ClientDataFinding } from "@/lib/backend-sector-guides";

import { FindingMark } from "./guide-view";

type Marks = Map<string, ClientDataFinding[]>;

/**
 * Spec 047 (58.4, 58.5): the tests generated with a client's guide, each one
 * with its fields. A test that carries client data opens by itself, with the
 * data marked where it is.
 */
export function GeneratedTests({ tests, marks }: { tests: SectorTest[]; marks: Marks }) {
  if (!tests.length) {
    return <p className="text-sm text-muted-foreground text-pretty">No tiene pruebas. Corrígela y escribe sus 12 antes de revisarla.</p>;
  }
  return (
    <ol aria-label="Pruebas de la guía" className="flex flex-col divide-y divide-border rounded-md ring-1 ring-foreground/10">
      {tests.map((t, i) => (
        <li key={`${i}:${t.key}`} className="min-w-0">
          <TestDetails test={t} index={i} marks={marks} />
        </li>
      ))}
    </ol>
  );
}

function TestDetails({ test, index, marks }: { test: SectorTest; index: number; marks: Marks }) {
  const base = `/tests/${index}`;
  const marked = [...marks.keys()].some((k) => k === base || k.startsWith(`${base}/`));
  const state = test.expected_state ?? {};
  const mark = (field: string, node: ReactNode) => (
    <FindingMark path={`${base}/${field}`} marks={marks}>
      {node}
    </FindingMark>
  );
  return (
    <details open={marked || undefined}>
      <summary className="flex min-h-12 cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <span className="w-6 shrink-0 text-xs text-muted-foreground tabular-nums">{index + 1}</span>
        <span className="min-w-0 flex-1">
          <span className="font-medium break-words">{test.name}</span> <code className="text-xs text-muted-foreground break-all">{test.key}</code>
        </span>
        {marked ? <StatusBadge tone="danger">Dato del cliente</StatusBadge> : null}
        {test.critical ? <StatusBadge tone="warning">Crítica</StatusBadge> : null}
      </summary>
      <div className="px-4 pb-4">
        <DescriptionList
          layout="inline"
          items={[
            { key: "name", term: "Nombre", detail: mark("name", test.name) },
            { key: "persona", term: "Persona simulada", detail: mark("persona", test.persona || "—") },
            { key: "first", term: "Primer mensaje", detail: mark("first_message", <q>{test.first_message}</q>) },
            { key: "plan", term: "Plan", detail: mark("plan", test.plan || "—") },
            {
              key: "state",
              term: "Estado esperado",
              detail: mark(
                "expected_state",
                Object.keys(state).length ? (
                  <pre className="overflow-x-auto font-mono text-xs">{JSON.stringify(state, null, 2)}</pre>
                ) : (
                  <span className="text-muted-foreground">Sin estado que comprobar: decide el juez.</span>
                ),
              ),
            },
            {
              key: "criteria",
              term: "Criterios",
              detail: mark(
                "criteria",
                <ul className="flex flex-col gap-1">
                  {test.criteria.map((c, j) => (
                    <li key={`${j}:${c.key}`} className="text-pretty">
                      <FindingMark path={`${base}/criteria/${j}`} marks={marks}>
                        <code className="text-xs text-muted-foreground">{c.key}</code> {c.text}
                      </FindingMark>
                    </li>
                  ))}
                </ul>,
              ),
            },
          ]}
        />
      </div>
    </details>
  );
}
