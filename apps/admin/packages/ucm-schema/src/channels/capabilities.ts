/**
 * Capability matrix per channel.
 *
 * For each channel we declare which UCM capabilities can be rendered natively,
 * and the channel-specific structural limits that the validator enforces.
 *
 * Adding a new channel = new entry here + a renderer + (optionally) a stricter
 * validator. Nothing else in the schema package needs to change.
 */
import type { CapabilityKey } from "../types.js";

export type ChannelName =
  | "web"
  | "whatsapp"
  | "instagram"
  | "messenger"
  | "voice";

export type ChannelLimits = {
  /** Max number of buttons in a `quick_replies` message. */
  quickRepliesMaxButtons?: number;
  /** Max characters in a quick-reply button title. */
  quickRepliesTitleMaxChars?: number;
  /** Max total rows across all sections in a `list` message. */
  listMaxRowsTotal?: number;
  /** Max characters in a list row title. */
  listRowTitleMaxChars?: number;
  /** Max characters in a list row description. */
  listRowDescriptionMaxChars?: number;
  /** Max characters in the list "open" button text. */
  listButtonTextMaxChars?: number;
  /** Max characters in a `cta_url` button title. */
  ctaUrlButtonTitleMaxChars?: number;
  /** Max characters in any text body (text, body of interactive, media caption). */
  textBodyMaxChars?: number;
  /** Maximum nesting depth for a `composite` message. */
  compositeMaxDepth?: number;
};

export type ChannelProfile = {
  name: ChannelName;
  capabilities: ReadonlySet<CapabilityKey>;
  limits: ChannelLimits;
};

const set = (...keys: CapabilityKey[]): ReadonlySet<CapabilityKey> =>
  new Set(keys);

// `web` — the Playground renderer and the future embed. Assume full support.
export const WEB: ChannelProfile = {
  name: "web",
  capabilities: set(
    "text",
    "text.markdown",
    "interactive.buttons",
    "interactive.list",
    "interactive.cta_url",
    "media.image",
    "media.video",
    "media.document",
    "media.audio",
    "location",
    "flow",
  ),
  limits: {
    textBodyMaxChars: 4096,
    compositeMaxDepth: 3,
  },
};

// `whatsapp` — Cloud API limits. These are the binding ones in production.
// Reference: WhatsApp Business Platform Cloud API docs.
export const WHATSAPP: ChannelProfile = {
  name: "whatsapp",
  capabilities: set(
    "text",
    // markdown is not natively supported — Cloud API uses its own minimal
    // formatting (*bold*, _italic_, ~strike~) but we treat that as `text` and
    // let the renderer downgrade markdown.
    "interactive.buttons",
    "interactive.list",
    "interactive.cta_url",
    "media.image",
    "media.video",
    "media.document",
    "media.audio",
    "location",
    "flow",
  ),
  limits: {
    quickRepliesMaxButtons: 3,
    quickRepliesTitleMaxChars: 20,
    listMaxRowsTotal: 10,
    listRowTitleMaxChars: 24,
    listRowDescriptionMaxChars: 72,
    listButtonTextMaxChars: 20,
    ctaUrlButtonTitleMaxChars: 20,
    textBodyMaxChars: 1024,
    compositeMaxDepth: 1,
  },
};

// `instagram` — DM API supports text and media; no rich interactive primitives.
export const INSTAGRAM: ChannelProfile = {
  name: "instagram",
  capabilities: set(
    "text",
    "interactive.buttons",
    "media.image",
    "media.video",
  ),
  limits: {
    quickRepliesMaxButtons: 13,
    quickRepliesTitleMaxChars: 20,
    textBodyMaxChars: 1000,
    compositeMaxDepth: 1,
  },
};

// `messenger` — Meta Messenger Platform.
export const MESSENGER: ChannelProfile = {
  name: "messenger",
  capabilities: set(
    "text",
    "interactive.buttons",
    "interactive.cta_url",
    "media.image",
    "media.video",
    "media.audio",
    "media.document",
  ),
  limits: {
    quickRepliesMaxButtons: 13,
    quickRepliesTitleMaxChars: 20,
    ctaUrlButtonTitleMaxChars: 20,
    textBodyMaxChars: 2000,
    compositeMaxDepth: 1,
  },
};

// `voice` — out of MVP scope but declared so UCM is voice-aware today.
// Only plain text survives; everything else must degrade to fallback_text.
export const VOICE: ChannelProfile = {
  name: "voice",
  capabilities: set("text"),
  limits: {
    textBodyMaxChars: 600,
    compositeMaxDepth: 1,
  },
};

export const CHANNELS: Readonly<Record<ChannelName, ChannelProfile>> = {
  web: WEB,
  whatsapp: WHATSAPP,
  instagram: INSTAGRAM,
  messenger: MESSENGER,
  voice: VOICE,
};

export function getChannel(name: ChannelName): ChannelProfile {
  const profile = CHANNELS[name];
  if (!profile) {
    throw new Error(`Unknown channel: ${name}`);
  }
  return profile;
}

export function channelSupports(
  channel: ChannelProfile,
  capability: CapabilityKey,
): boolean {
  return channel.capabilities.has(capability);
}

/**
 * Capabilities required by a UCM payload, independent of channel.
 *
 * The agent should set `capabilities_required` on the UCM message itself,
 * but we recompute here so we can be tolerant of payloads from older
 * versions or from agents that forget to set the field.
 */
export function inferCapabilities(
  type: string,
  content: Record<string, unknown>,
): CapabilityKey[] {
  switch (type) {
    case "text": {
      const fmt =
        typeof content?.format === "string" ? content.format : "plain";
      return fmt === "markdown" ? ["text", "text.markdown"] : ["text"];
    }
    case "quick_replies":
      return ["interactive.buttons"];
    case "list":
      return ["interactive.list"];
    case "cta_url":
      return ["interactive.cta_url"];
    case "media": {
      const kind = String(content?.kind ?? "image");
      return [`media.${kind}` as CapabilityKey];
    }
    case "location":
      return ["location"];
    case "flow":
      return ["flow"];
    case "composite":
      return [];
    default:
      return [];
  }
}
