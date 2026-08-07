/**
 * Channel role helpers — deliberately free of `server-only`.
 *
 * These read two operator-editable flags out of `channels.config`, and the
 * components that need them are client components (the number list on the
 * connectors page). `lib/backend.ts` imports `server-only`, so anything a
 * client component needs as a *value* — not just a type — cannot live there.
 *
 * They mirror `config_role` / `config_agent_enabled` in
 * `nexus_api/services/channel_routing.py`. Keep the defaults identical: an
 * absent flag means "behave as before roles existed", and an unknown role
 * reads as untagged rather than taking a live channel out of service.
 */

export type ChannelRole = "agent" | "notifications";

type WithConfig = { config: Record<string, unknown> | null | undefined };

/** Declared role, or null when untagged. An unknown value reads as untagged. */
export function channelRole(channel: WithConfig): ChannelRole | null {
  const raw = channel.config?.role;
  return raw === "agent" || raw === "notifications" ? raw : null;
}

/** Only an explicit `false` makes a channel send-only. */
export function channelAgentEnabled(channel: WithConfig): boolean {
  return channel.config?.agent_enabled !== false;
}
