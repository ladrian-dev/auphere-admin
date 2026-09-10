import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { InviteButton } from "@/components/team/invite-dialog";
import { LocalExecCeiling } from "@/components/team/local-exec-ceiling";
import { TeamLists } from "@/components/team/team-lists";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

export const metadata = { title: "Equipo" };

export default async function TeamPage() {
  const principal = await requirePrincipal("/team");
  if (!can(principal.role, "team:read")) redirect("/");
  const { t } = await getT(principal.locale);
  const backend = backendFor(principal);
  const team = await backend.team();
  const manage = can(principal.role, "team:manage");
  // Spec 003: el techo de ejecución local del partner. Se lee siempre —saber
  // qué techo hay puesto explica por qué te siguen preguntando— y solo lo
  // cambian owner y admin (`teammates:policy`).
  const ceiling = await backend.localExecCeiling();
  return (
    <>
      <PageHeader eyebrow={t("nav.group.account")} title={t("team.title")} description={t("team.description")} actions={manage ? <InviteButton origin={process.env.NEXUS_CONSOLE_ORIGIN ?? ""} /> : undefined} />
      <TeamLists team={team} manage={manage} />
      <div className="mt-6">
        <LocalExecCeiling ceiling={ceiling.ceiling} manage={can(principal.role, "teammates:policy")} />
      </div>
    </>
  );
}
