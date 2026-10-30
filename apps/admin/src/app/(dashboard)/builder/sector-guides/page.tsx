import { Suspense } from "react";

import { PageHeader, Section } from "@nexus/ui";
import { sectorGuidesBackend } from "@/lib/backend-sector-guides";

import { BuilderTabs } from "../builder-tabs";
import { AuphereGuides } from "./auphere-guides";
import { load } from "./load";
import { MissingLabels } from "./missing-labels";
import { SectionError } from "./section-error";
import { parseLimit } from "./sector-guides";
import { AuphereGuidesSkeleton, MissingLabelsSkeleton } from "./skeletons";

export const metadata = { title: "Sectores sin guía" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T201, 58.5): the sector labels of clients of «Otro» that have no
 * Auphere guide, the most repeated first, with the guides the builder
 * generated for each client, and Auphere's guides. Each part is read on its
 * own: the list is worked out client by client and can take a few seconds, and
 * one that fails does not take the other with it.
 */
export default async function SectorGuidesPage({ searchParams }: { searchParams: Promise<{ limit?: string | string[] }> }) {
  const { limit: raw } = await searchParams;
  const limit = parseLimit(raw);
  return (
    <>
      <PageHeader
        title="Sectores sin guía"
        description="Cuando el sector de un cliente no tiene guía de Auphere, el constructor genera una solo para él, con sus 12 pruebas. Aquí se ven las etiquetas que más se repiten. Una guía generada, revisada y sin datos del cliente se puede convertir en guía de Auphere."
      />
      <BuilderTabs current="/builder/sector-guides" />
      <Section
        title="Las etiquetas sin guía que más se repiten"
        description="Clientes cuyo sector guardado es «Otro», por su etiqueta normalizada. Un cliente sin sector todavía no cuenta."
      >
        <Suspense key={limit} fallback={<MissingLabelsSkeleton />}>
          <Missing limit={limit} />
        </Suspense>
      </Section>
      <Section
        title="Guías de Auphere"
        description="Las de las plantillas, en el orden de los sectores, y después las convertidas. Un cliente de «Otro» cuya etiqueta tiene una convertida la recibe en lugar de generar la suya."
      >
        <Suspense fallback={<AuphereGuidesSkeleton />}>
          <Guides />
        </Suspense>
      </Section>
    </>
  );
}

async function Missing({ limit }: { limit: number }) {
  const read = await load(() => sectorGuidesBackend.missing(limit));
  if (!read.ok || !read.data) {
    return <SectionError title="No se pudieron leer los sectores sin guía" status={read.ok ? null : read.status} />;
  }
  return <MissingLabels data={read.data} limit={limit} />;
}

async function Guides() {
  const read = await load(() => sectorGuidesBackend.guides());
  if (!read.ok || !read.data) {
    return <SectionError title="No se pudieron leer las guías de Auphere" status={read.ok ? null : read.status} />;
  }
  return <AuphereGuides guides={read.data.items} />;
}
