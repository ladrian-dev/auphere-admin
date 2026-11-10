"use client";

import { useState } from "react";

import { StatusBadge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@nexus/ui";
import type { CalibrationItem } from "@/lib/backend-builder";

import { VERDICT_LABEL } from "../labels";

/**
 * Spec 047 (T087, 21.8): each labelled criterion of the set — what a person
 * said, what the judge said, and whether they agree. The disagreements are
 * what to read first.
 */
export function CalibrationItems({ items }: { items: CalibrationItem[] }) {
  const [onlyMisses, setOnlyMisses] = useState(false);
  if (!items.length) {
    return <p className="text-sm text-muted-foreground">Este informe no guarda los ejemplos.</p>;
  }
  const misses = items.filter((i) => !i.match).length;
  const rows = onlyMisses ? items.filter((i) => !i.match) : items;
  return (
    <div className="flex flex-col gap-3">
      <label className="flex min-h-6 w-fit items-center gap-2 text-sm">
        <input type="checkbox" className="size-4 accent-primary" checked={onlyMisses} onChange={(e) => setOnlyMisses(e.target.checked)} />
        Solo los desacuerdos ({misses})
      </label>
      {rows.length ? (
        <Table aria-label="Ejemplos de la calibración">
          <TableHeader>
            <TableRow>
              <TableHead>Ejemplo</TableHead>
              <TableHead>Criterio</TableHead>
              <TableHead>Etiqueta humana</TableHead>
              <TableHead>Juez</TableHead>
              <TableHead>Resultado</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => (
              <TableRow key={`${item.id}:${item.key}`}>
                <TableCell>
                  <code className="text-xs">{item.id}</code>
                </TableCell>
                <TableCell>
                  <code className="text-xs">{item.key}</code>
                </TableCell>
                <TableCell>{VERDICT_LABEL[item.label] ?? item.label}</TableCell>
                <TableCell>{VERDICT_LABEL[item.judge] ?? item.judge}</TableCell>
                <TableCell>
                  <StatusBadge tone={item.match ? "positive" : "danger"}>{item.match ? "Coincide" : "No coincide"}</StatusBadge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <p className="text-sm text-muted-foreground">El juez coincide con las personas en todos los criterios.</p>
      )}
    </div>
  );
}
