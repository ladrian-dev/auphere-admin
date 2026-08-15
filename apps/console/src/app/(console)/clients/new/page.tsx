import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { NewClientForm } from "./new-client-form";

export const metadata = { title: "Nuevo cliente" };

export default async function NewClientPage() {
  const principal = await requirePrincipal("/clients/new");
  if (!can(principal.role, "clients:write")) redirect("/clients");
  const { t } = await getT(principal.locale);
  const me = await backendFor(principal).me();
  return (
    <>
      <PageHeader eyebrow={t("nav.clients")} title={t("clients.create.title")} description={t("clients.create.body")} />
      <NewClientForm quota={me.quota} />
    </>
  );
}
