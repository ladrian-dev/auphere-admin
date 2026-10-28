import { notFound, redirect } from "next/navigation";

import { channelHref } from "@/components/builder/channel-model";
import { ChannelConfigPage } from "@/components/builder/channel-page";
import { clientHref } from "@/components/shell/routes-v2";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getClientV2Cached, getConsoleVersionCached } from "../../../../data";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("builder.screen.channels") };
}

/**
 * La página de configuración de un canal (spec 047, historia 11; requisitos 32
 * y 33; T115): a quién responde, excepciones, escalado, mensaje de espera y
 * comprobaciones, con su barra de guardar, su historial y su ⋯. Cuelga de su
 * agente: «Clientes › {cliente} › {agente} › Canal {número}».
 *
 * Solo con la consola nueva (con la de hoy, la audiencia sigue en el agente).
 * Si el número ya lo atiende otro agente, se va a su dirección. Un canal de
 * otro cliente es un 404.
 */
export default async function ChannelConfigRoute({ params }: { params: Promise<{ ref: string; agentId: string; channelId: string }> }) {
  const { ref, agentId, channelId } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/agents/${agentId}/channels/${channelId}`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(`/clients/${encodeURIComponent(ref)}/channels`);
  if (!can(principal.role, "channels:read")) redirect(clientHref(ref));
  if (!UUID_RE.test(agentId) || !UUID_RE.test(channelId)) notFound();

  const api = backendFor(principal);
  const [page, history, client] = await Promise.all([
    run(() => api.getChannelPage(ref, channelId)),
    run(() => api.getChannelHistory(ref, channelId)),
    run(() => getClientV2Cached(principal, ref)),
  ]);
  if (!page.ok) {
    if (page.status === 404 || page.status === 422) notFound();
    throw new Error(`channel page ${page.status}`);
  }
  // Pasó a otro agente: su página cuelga de él.
  if (page.data.agent && page.data.agent.id !== agentId) redirect(channelHref(ref, page.data.agent.id, channelId));
  // Spec 047 (45.1): «Asignar saldo» se abre aquí mismo si esta persona puede
  // (la acción del ⋯ del cliente); si no, «Pedir saldo» (45.7).
  const allowed = client.ok ? client.data.allowed : [];
  const balance = client.ok
    ? allowed.includes("assign_balance")
      ? { name: client.data.name, mode: "assign" as const }
      : allowed.includes("request_balance")
        ? { name: client.data.name, mode: "request" as const }
        : null
    : null;
  return (
    <ChannelConfigPage
      key={`${channelId}:${agentId}`}
      refId={ref}
      agentId={agentId}
      page={page.data}
      history={history.ok ? history.data : null}
      canWrite={can(principal.role, "channels:write")}
      balance={balance}
    />
  );
}
