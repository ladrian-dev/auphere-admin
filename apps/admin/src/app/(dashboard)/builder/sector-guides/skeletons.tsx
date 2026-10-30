import type { ReactNode } from "react";

import { Skeleton } from "@nexus/ui";

/**
 * Spec 047 (T201): the skeletons of «Sectores sin guía», with the size of what
 * they stand for — a card per label with two candidates, a row per Auphere
 * guide, and a generated guide's notices, guide and 12 tests. The list is
 * worked out client by client and can take a few seconds.
 */

function LabelCardBlock() {
  return (
    <div className="flex flex-col gap-3 rounded-md p-4 ring-1 ring-foreground/10">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-5 w-48" />
      </div>
      <div className="flex flex-col divide-y divide-border border-t border-border">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 pt-3 pb-1">
            <div className="flex flex-1 flex-col gap-1">
              <Skeleton className="h-6 w-56" />
              <Skeleton className="h-4 w-72 max-w-full" />
            </div>
            <Skeleton className="h-8 w-20" />
          </div>
        ))}
      </div>
    </div>
  );
}

function MissingBlocks() {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-4 w-64" />
      {Array.from({ length: 3 }).map((_, i) => (
        <LabelCardBlock key={i} />
      ))}
    </div>
  );
}

function GuideRowsBlock() {
  return (
    <div className="flex flex-col divide-y divide-border rounded-md ring-1 ring-foreground/10">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex min-h-12 items-center gap-3 px-4 py-3">
          <Skeleton className="size-4" />
          <Skeleton className="h-5 flex-1" />
          <Skeleton className="h-6 w-20" />
          <Skeleton className="h-4 w-32" />
        </div>
      ))}
    </div>
  );
}

function SectionFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-5 w-64" />
        <Skeleton className="h-4 w-full max-w-xl" />
      </div>
      {children}
    </div>
  );
}

/** The labels without a guide, while the API works them out. */
export function MissingLabelsSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Cargando las etiquetas sin guía">
      <MissingBlocks />
    </div>
  );
}

/** Auphere's guides, while they are read. */
export function AuphereGuidesSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Cargando las guías de Auphere">
      <GuideRowsBlock />
    </div>
  );
}

/** The whole page body, for `loading.tsx`. */
export function SectorGuidesSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Cargando los sectores sin guía" className="flex flex-col gap-6">
      <div className="flex gap-1 border-b border-border pb-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-6 w-32" />
        ))}
      </div>
      <SectionFrame>
        <MissingBlocks />
      </SectionFrame>
      <SectionFrame>
        <GuideRowsBlock />
      </SectionFrame>
    </div>
  );
}

/** One generated guide: its status, the guide and its 12 tests. */
export function GeneratedGuideSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Cargando la guía generada" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-4 w-64" />
        <Skeleton className="ml-auto h-8 w-56" />
      </div>
      <Skeleton className="h-16 w-full" />
      <SectionFrame>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="flex flex-col gap-2">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
          <div className="flex flex-col gap-2 lg:col-span-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-24 w-full" />
          </div>
        </div>
      </SectionFrame>
      <SectionFrame>
        <div className="flex flex-col divide-y divide-border rounded-md ring-1 ring-foreground/10">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-3">
              <Skeleton className="h-4 w-6" />
              <Skeleton className="h-5 flex-1" />
              <Skeleton className="h-6 w-16" />
            </div>
          ))}
        </div>
      </SectionFrame>
    </div>
  );
}
