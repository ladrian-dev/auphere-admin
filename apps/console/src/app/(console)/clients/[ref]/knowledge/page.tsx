import { redirect } from "next/navigation";

import { KnowledgeTable } from "@/components/agent-tools/knowledge-table";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

/** Knowledge (CP-15): upload/URL forms, document table, prompt-budget meter.
 *  Metadata only — the extracted text never reaches the console. */
export default async function KnowledgePage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "knowledge:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const data = await backendFor(principal).listKnowledge(ref);
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("knowledge.title")}>
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-base font-medium text-balance">{t("knowledge.title")}</h1>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("knowledge.description")}</p>
      </div>
      <KnowledgeTable refId={ref} data={data} canWrite={can(principal.role, "knowledge:write")} />
    </section>
  );
}
