import { redirect } from "next/navigation";

import { KnowledgeTable } from "@/components/agent-tools/knowledge-table";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getConsoleVersionCached } from "../data";

/** Knowledge (CP-15): upload/URL forms, document table, prompt-budget meter.
 *  Metadata only — the extracted text never reaches the console. */
export default async function KnowledgePage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal();
  if (!can(principal.role, "knowledge:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const [data, version] = await Promise.all([backendFor(principal).listKnowledge(ref), getConsoleVersionCached(principal)]);
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("knowledge.title")}>
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-base font-medium text-balance">{t("knowledge.title")}</h1>
        <p className=" text-sm text-pretty text-muted-foreground">{t("knowledge.description")}</p>
      </div>
      {/* Spec 047 (37.1): con la consola nueva cada agente tiene además su capa; aquí, la del negocio. */}
      <KnowledgeTable
        refId={ref}
        data={data}
        canWrite={can(principal.role, "knowledge:write")}
        layerNote={version === "v2" ? t("knowledge.layer.business") : undefined}
      />
    </section>
  );
}
