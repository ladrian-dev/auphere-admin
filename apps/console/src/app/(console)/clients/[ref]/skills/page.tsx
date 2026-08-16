import { redirect } from "next/navigation";

import { SkillsGrid } from "@/components/agent-tools/skills-grid";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

/** Vertical skills (CP-14): cards with a toggle; saving edits the draft. */
export default async function SkillsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const data = await backendFor(principal).listSkills(ref);
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("skills.title")}>
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-base font-medium text-balance">{t("skills.title")}</h1>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("skills.description")}</p>
      </div>
      <SkillsGrid refId={ref} data={data} canWrite={can(principal.role, "agents:write")} />
    </section>
  );
}
