import Link from "next/link";

import { EmptyState, PageHeader, buttonVariants } from "@nexus/ui";
import { CrumbName } from "@/components/shell/crumb-names";
import { sectorGuidesBackend } from "@/lib/backend-sector-guides";
import { requireOperator } from "@/lib/session";

import { DATE } from "../../../labels";
import { GeneratedGuideView } from "../../generated-guide";
import { load } from "../../load";
import { SectionError } from "../../section-error";
import { LIST_PATH } from "../../sector-guides";

export const metadata = { title: "Guía generada" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T201, 58.5): one guide the builder generated for a client whose
 * sector has no Auphere guide. Auphere reviews it here — corrects it, and the
 * API checks it carries no client data — and converts it into an Auphere guide.
 */
export default async function GeneratedGuidePage({ params }: { params: Promise<{ tenantId: string; guideId: string }> }) {
  const { tenantId, guideId } = await params;
  const [operator, read, guides] = await Promise.all([
    requireOperator(),
    load(() => sectorGuidesBackend.generated(tenantId, guideId)),
    // Only to warn early of a key already taken; the API checks it anyway.
    load(() => sectorGuidesBackend.guides()),
  ]);

  const back = (
    <Link href={LIST_PATH} className={buttonVariants({ variant: "outline", size: "sm" })}>
      Volver a los sectores sin guía
    </Link>
  );

  if (!read.ok) {
    return (
      <>
        <PageHeader title="Guía generada" />
        <SectionError title="No se pudo leer la guía generada" status={read.status} />
      </>
    );
  }
  const guide = read.data;
  if (!guide) {
    return (
      <>
        <PageHeader title="Guía generada" />
        <EmptyState
          title="Esa guía no existe"
          description="El cliente no existe o la guía no es suya. Puede que se archivara o que el enlace sea de otra instancia."
          action={back}
        />
      </>
    );
  }

  const takenKeys = ["otro", ...(guides.ok && guides.data ? guides.data.items.map((g) => g.key) : [])];
  return (
    <>
      <CrumbName id={guideId} label={`${guide.sector_label} · ${guide.client_name}`} />
      <PageHeader
        title={guide.sector_label}
        description={`Guía generada para ${guide.client_name} el ${DATE.format(new Date(guide.created_at))}, con la etiqueta «${guide.label_key}». Es del cliente: nadie más la ve hasta que se convierta en guía de Auphere.`}
        actions={back}
      />
      {/* A new saved state (reviewed again, converted) starts the view again: no stale corrections or findings. */}
      <GeneratedGuideView
        key={`${guide.status}:${guide.reviewed_at ?? ""}:${guide.promoted_at ?? ""}`}
        guide={guide}
        operatorEmail={operator.email}
        takenKeys={takenKeys}
      />
    </>
  );
}
