import { notFound, redirect } from "next/navigation";

import { channelHref } from "@/components/builder/channel-model";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getConsoleVersionCached } from "../../data";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Spec 047 (historia 11): la dirección de un canal desde el cliente
 * (`/clients/{ref}/channels/{id}`, la que usan los avisos y la página de
 * Canales). La página de verdad cuelga de su agente: aquí solo se busca cuál y
 * se va allí. Con la consola de hoy, o sin agente, a los canales del cliente.
 */
export default async function ChannelOfClientPage({ params }: { params: Promise<{ ref: string; channelId: string }> }) {
  const { ref, channelId } = await params;
  const channels = `/clients/${encodeURIComponent(ref)}/channels`;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/channels/${channelId}`);
  if (!can(principal.role, "channels:read")) redirect(`/clients/${encodeURIComponent(ref)}`);
  if (!UUID_RE.test(channelId)) notFound();
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(channels);
  const page = await run(() => backendFor(principal).getChannelPage(ref, channelId));
  if (!page.ok) {
    if (page.status === 404 || page.status === 422) notFound();
    throw new Error(`channel page ${page.status}`);
  }
  redirect(page.data.agent ? channelHref(ref, page.data.agent.id, channelId) : channels);
}
