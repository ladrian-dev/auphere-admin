import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { KeysList } from "@/components/keys/keys-list";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

export const metadata = { title: "Claves de API" };

export default async function KeysPage() {
  const principal = await requirePrincipal("/keys");
  if (!can(principal.role, "keys:read")) redirect("/");
  const { t } = await getT(principal.locale);
  const keys = await backendFor(principal).listKeys();
  return (
    <>
      <PageHeader eyebrow={t("nav.group.account")} title={t("keys.title")} description={t("keys.description")} />
      <KeysList keys={keys} manage={can(principal.role, "keys:manage")} />
    </>
  );
}
