import { redirect } from "next/navigation";

import { getT } from "@/i18n/server";
import { can, requirePrincipal } from "@/lib/principal";

import { getClientCached } from "../data";
import { SettingsForm } from "./settings-form";

export default async function SettingsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "clients:write")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const client = await getClientCached(principal, ref);
  return (
    <section className="flex max-w-lg flex-col gap-6" aria-label={t("clients.settings.title")}>
      <SettingsForm refId={ref} name={client.name} timezone={client.timezone} />
    </section>
  );
}
