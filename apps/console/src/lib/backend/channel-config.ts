import type { Call } from "../backend";

import { ifMatch } from "./agent-draft";
import type { AgentChannels, ChannelChange, ChannelConfigIn, ChannelPage, InstagramComments, OwnerLink, OwnerLinkMode } from "./channel-config-types";

/**
 * Carril de la página de cada canal, de su menú ⋯ y del enlace del dueño por
 * agente (spec 047, historias 10 y 11; T111, T112, T114 y T115):
 * `contracts/console-api.md` §5. Se esparce en `backendFor`.
 *
 * Guardar exige la revisión que leyó la pantalla (`If-Match`). Los errores
 * llegan como `BackendError` con su código: `revision_conflict` (412, con
 * `current` y `changes`), `revision_required` (428),
 * `channel_test_numbers_required`, `invalid_phone` (con `value`),
 * `too_many_recipients` (422), `agent_not_published` (con `fix: publish_agent`),
 * `bag_empty` (con `fix: assign_balance`), `audience_admin_only_template` y
 * `undo_window_closed` (409); en el enlace del dueño, `link_pending_exists`
 * (con `link_id`) y `whatsapp_login_unavailable` (409).
 *
 * Desconectar sigue en `channels.ts` (`disconnectChannel`).
 */

export * from "./channel-config-types";

export function channelConfigApi(call: Call) {
  const enc = encodeURIComponent;
  const client = (ref: string) => `/console/clients/${enc(ref)}`;
  const channel = (ref: string, channelId: string) => `${client(ref)}/channels/${enc(channelId)}`;
  const agent = (ref: string, agentId: string) => `${client(ref)}/agents/${enc(agentId)}`;
  return {
    getChannelPage: (ref: string, channelId: string) => call<ChannelPage>(channel(ref, channelId)),
    saveChannelConfig: (ref: string, channelId: string, revision: number, config: ChannelConfigIn) =>
      call<ChannelPage>(`${channel(ref, channelId)}/config`, { method: "PUT", body: config, headers: ifMatch(revision) }),
    undoChannelConfig: (ref: string, channelId: string) => call<ChannelPage>(`${channel(ref, channelId)}/config/undo`, { method: "POST" }),
    getChannelHistory: (ref: string, channelId: string) => call<ChannelChange[]>(`${channel(ref, channelId)}/history`),
    moveChannel: (ref: string, channelId: string, toAgentId: string) =>
      call<ChannelPage>(`${channel(ref, channelId)}/move`, { method: "POST", body: { to_agent_id: toAgentId } }),
    pauseChannel: (ref: string, channelId: string) => call<ChannelPage>(`${channel(ref, channelId)}/pause`, { method: "POST" }),
    resumeChannel: (ref: string, channelId: string) => call<ChannelPage>(`${channel(ref, channelId)}/resume`, { method: "POST" }),
    setInstagramComments: (ref: string, channelId: string, body: InstagramComments) =>
      call<ChannelPage>(`${channel(ref, channelId)}/comments`, { method: "PUT", body }),

    listAgentChannels: (ref: string, agentId: string) => call<AgentChannels>(`${agent(ref, agentId)}/channels`),
    createOwnerLink: (ref: string, agentId: string, body: { mode: OwnerLinkMode; replace?: boolean }) =>
      call<OwnerLink>(`${agent(ref, agentId)}/channels/owner-links`, { method: "POST", body }),
    revokeOwnerLink: (ref: string, agentId: string, linkId: string) =>
      call<null>(`${agent(ref, agentId)}/channels/owner-links/${enc(linkId)}`, { method: "DELETE" }),
  };
}
