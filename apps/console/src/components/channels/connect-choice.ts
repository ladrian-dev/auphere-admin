/**
 * Which control the Channels page shows for «connect WhatsApp» (spec 016,
 * R1.1/R1.3). Pure, so the decision is testable without rendering a server
 * component:
 *
 * - ``none``       — the member cannot manage channels: nothing to click.
 * - ``connect``    — Meta is configured: the real Embedded Signup button.
 * - ``by_auphere`` — the environment has no Meta app or config id: a note
 *                    that says who connects it and what to send. No button.
 */
import type { MetaSignupConfig } from "./whatsapp-connect";

export type ConnectChoice = "none" | "connect" | "by_auphere";

export function metaIsConfigured(meta: MetaSignupConfig): boolean {
  return !!meta.appId && !!(meta.configIdCloudApi || meta.configIdCoexistence);
}

export function connectChoice({ manage, meta }: { manage: boolean; meta: MetaSignupConfig }): ConnectChoice {
  if (!manage) return "none";
  return metaIsConfigured(meta) ? "connect" : "by_auphere";
}

/** The subset of the environment the button needs — never the secret. */
export function metaSignupConfig(env: {
  NEXUS_META_APP_ID?: string;
  NEXUS_META_GRAPH_API_VERSION: string;
  NEXUS_META_CONFIG_ID_WA_CLOUD_API?: string;
  NEXUS_META_CONFIG_ID_WA_COEXISTENCE?: string;
}): MetaSignupConfig {
  return {
    appId: env.NEXUS_META_APP_ID ?? null,
    graphVersion: env.NEXUS_META_GRAPH_API_VERSION,
    configIdCloudApi: env.NEXUS_META_CONFIG_ID_WA_CLOUD_API ?? null,
    configIdCoexistence: env.NEXUS_META_CONFIG_ID_WA_COEXISTENCE ?? null,
  };
}
