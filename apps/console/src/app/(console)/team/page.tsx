import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { InviteButton } from "@/components/team/invite-dialog";
import { TeamLists } from "@/components/team/team-lists";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("nav.team");

export default async function TeamPage() {
  const principal = await requirePartnerPrincipal("/team");
  if (!can(principal.role, "team:read")) redirect("/");
  const { t } = await getT(principal.locale);
  const backend = backendFor(principal);
  const team = await backend.team();
  const manage = can(principal.role, "team:manage");
  return (
    <>
      <PageHeader eyebrow={t("nav.group.account")} title={t("team.title")} description={t("team.description")} actions={manage ? <InviteButton origin={process.env.NEXUS_CONSOLE_ORIGIN ?? ""} /> : undefined} />
      <TeamLists team={team} manage={manage} />
    </>
  );
}
