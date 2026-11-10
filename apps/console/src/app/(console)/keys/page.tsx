import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { KeysList, NewKeyButton } from "@/components/keys/keys-list";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("nav.keys");

export default async function KeysPage() {
  const principal = await requirePartnerPrincipal("/keys");
  if (!can(principal.role, "keys:read")) redirect("/");
  const { t } = await getT(principal.locale);
  const keys = await backendFor(principal).listKeys();
  const manage = can(principal.role, "keys:manage");
  return (
    <>
      {/* Spec 047 (prototipo): «Nueva clave» en la cabecera de la página. */}
      <PageHeader size="display" title={t("keys.title")} description={t("keys.description")} actions={manage ? <NewKeyButton /> : undefined} />
      <KeysList keys={keys} manage={manage} />
    </>
  );
}
