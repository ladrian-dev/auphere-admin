import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { InviteButton } from "@/components/team/invite-dialog";
import { TeamLists } from "@/components/team/team-lists";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

export const metadata = { title: "Equipo" };

export default async function TeamPage() {
  const principal = await requirePrincipal("/team");
  if (!can(principal.role, "team:read")) redirect("/");
  const { t } = await getT(principal.locale);
  const team = await backendFor(principal).team();
  const manage = can(principal.role, "team:manage");
  return (
    <>
      <PageHeader eyebrow={t("nav.group.account")} title={t("team.title")} description={t("team.description")} actions={manage ? <InviteButton origin={process.env.NEXUS_CONSOLE_ORIGIN ?? ""} /> : undefined} />
      <TeamLists team={team} manage={manage} />
    </>
  );
}
