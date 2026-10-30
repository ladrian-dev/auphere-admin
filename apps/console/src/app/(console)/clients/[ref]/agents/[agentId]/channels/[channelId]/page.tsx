import { notFound, permanentRedirect } from "next/navigation";

import { channelHref } from "@/components/builder/channel-model";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * La dirección vieja de la configuración de un canal (spec 047, historia 11).
 * Desde el requisito 63.1 (hueco H5) la configuración se pinta dentro de su
 * agente, en la pestaña Canales (`?canal=`): esta ruta solo redirige allí (308). La
 * pantalla del agente comprueba la sesión, los permisos, que el número sea de
 * este cliente y, si es de otro agente, lleva al suyo.
 */
export default async function ChannelConfigRoute({ params }: { params: Promise<{ ref: string; agentId: string; channelId: string }> }) {
  const { ref, agentId, channelId } = await params;
  if (!UUID_RE.test(agentId) || !UUID_RE.test(channelId)) notFound();
  permanentRedirect(channelHref(ref, agentId, channelId));
}
