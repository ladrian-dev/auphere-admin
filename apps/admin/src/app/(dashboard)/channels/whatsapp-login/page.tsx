import { notFound } from "next/navigation";

import { ErrorState, PageHeader } from "@nexus/ui";
import { loginBetaBackend } from "@/lib/backend-whatsapp-beta";
import { requireOperator } from "@/lib/session";

import { ChannelsTabs } from "../channels-tabs";
import { countryNames } from "./countries";
import { LoginBetaView } from "./login-beta-view";

export const metadata = { title: "Beta «WhatsApp login»" };
export const dynamic = "force-dynamic";

/**
 * Spec 047 (T117, 31.5, 31.6, 54.7): Auphere turns the «WhatsApp login» beta
 * on by country when Meta gives it to Auphere's app there, and never in the
 * EU or the EEA. Each change goes to the audit with who and why.
 *
 * Spec 059 (5.3): without Meta's configuration for signing up without an
 * account, the beta does not exist in this deployment — the page is «no
 * existe». A read that fails keeps its error state.
 */
export default async function WhatsappLoginBetaPage() {
  const [operator, beta] = await Promise.all([
    requireOperator(),
    loginBetaBackend.countries().catch(() => null),
  ]);
  if (beta !== null && !beta.configured) notFound();
  return (
    <>
      <PageHeader
        title="Beta «WhatsApp login»"
        description="Conectar WhatsApp sin cuenta de Meta, país por país, cuando Meta lo habilite para la app de Auphere. Nunca en la UE ni en el EEE."
      />
      <ChannelsTabs current="/channels/whatsapp-login" beta />
      {beta === null ? (
        <ErrorState title="No se pudo leer la beta por país" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <LoginBetaView countries={beta.countries} operatorId={operator.id} names={countryNames()} />
      )}
    </>
  );
}
