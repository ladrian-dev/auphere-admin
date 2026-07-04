/**
 * UCM (Universal Channel Message) v1.0.0
 *
 * Canonical schema for messages emitted by Nexus agents. Channel-agnostic by
 * design: every message carries enough structure to be rendered natively on
 * any supported channel (web, whatsapp, instagram, messenger, voice), and
 * enough fallback content to degrade gracefully when the channel cannot
 * render the native form.
 *
 * Reference: ADR-020 (`Auphere/nexus/decisions/ADR-020-qa-playground-ucm-multichannel.md`)
 */
import { z } from "zod";

export const UCM_VERSION = "1.0.0" as const;

// ---------- shared primitives ----------

const MessageId = z
  .string()
  .min(1)
  .max(128)
  .describe("Stable id for this UCM message — survives across channels.");

const NonEmptyShortString = z.string().min(1).max(1024);
// Plain-text message body. 4096 = WhatsApp Cloud API's real limit (the
// interactive bodies below stay at 1024, which Meta caps them to). Mirrors
// the Python schema's TextContent.body.
const TextBody = z.string().min(1).max(4096);
const FallbackText = z
  .string()
  .min(1)
  .max(4096)
  .describe(
    "Plain-text fallback. Required on every UCM — used when the channel cannot render the native form.",
  );

const Metadata = z.record(z.string(), z.unknown()).default({});

const CapabilityKey = z.enum([
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
]);
export type CapabilityKey = z.infer<typeof CapabilityKey>;

// ---------- type-specific content schemas ----------

const TextContent = z
  .object({
    body: TextBody,
    format: z.enum(["plain", "markdown"]).default("plain"),
  })
  .strict();

const QuickReplyButton = z
  .object({
    id: z.string().min(1).max(256),
    title: z.string().min(1).max(20),
  })
  .strict();

const QuickRepliesContent = z
  .object({
    body: NonEmptyShortString,
    buttons: z.array(QuickReplyButton).min(1).max(10),
  })
  .strict();

const ListRow = z
  .object({
    id: z.string().min(1).max(200),
    title: z.string().min(1).max(24),
    description: z.string().max(72).optional(),
  })
  .strict();

const ListSection = z
  .object({
    title: z.string().min(1).max(24),
    rows: z.array(ListRow).min(1).max(10),
  })
  .strict();

const ListContent = z
  .object({
    body: NonEmptyShortString,
    header: z.string().max(60).optional(),
    footer: z.string().max(60).optional(),
    button_text: z.string().min(1).max(20),
    sections: z.array(ListSection).min(1).max(10),
  })
  .strict();

const CtaUrlContent = z
  .object({
    body: NonEmptyShortString,
    button_title: z.string().min(1).max(20),
    url: z.string().url(),
  })
  .strict();

const MediaKind = z.enum(["image", "video", "document", "audio"]);
export type MediaKind = z.infer<typeof MediaKind>;

const MediaContent = z
  .object({
    kind: MediaKind,
    url: z.string().url(),
    caption: z.string().max(1024).optional(),
    filename: z.string().max(255).optional(),
    mime_type: z.string().max(127).optional(),
  })
  .strict();

const LocationContent = z
  .object({
    latitude: z.number().gte(-90).lte(90),
    longitude: z.number().gte(-180).lte(180),
    name: z.string().max(255).optional(),
    address: z.string().max(255).optional(),
  })
  .strict();

const FlowContent = z
  .object({
    flow_id: z.string().min(1).max(255),
    body: z.string().max(1024).optional(),
    header_text: z.string().max(60).optional(),
    footer_text: z.string().max(60).optional(),
    button_text: z.string().min(1).max(20),
    screen: z.string().max(60).optional(),
    data: z.record(z.string(), z.unknown()).optional(),
  })
  .strict();

// ---------- base UCM and discriminated union ----------

const BaseUCMShape = {
  ucm_version: z.literal(UCM_VERSION),
  message_id: MessageId,
  capabilities_required: z.array(CapabilityKey).default([]),
  fallback_text: FallbackText,
  metadata: Metadata,
};

export const TextUCM = z
  .object({
    ...BaseUCMShape,
    type: z.literal("text"),
    content: TextContent,
  })
  .strict();

export const QuickRepliesUCM = z
  .object({
    ...BaseUCMShape,
    type: z.literal("quick_replies"),
    content: QuickRepliesContent,
  })
  .strict();

export const ListUCM = z
  .object({
    ...BaseUCMShape,
    type: z.literal("list"),
    content: ListContent,
  })
  .strict();

export const CtaUrlUCM = z
  .object({
    ...BaseUCMShape,
    type: z.literal("cta_url"),
    content: CtaUrlContent,
  })
  .strict();

export const MediaUCM = z
  .object({
    ...BaseUCMShape,
    type: z.literal("media"),
    content: MediaContent,
  })
  .strict();

export const LocationUCM = z
  .object({
    ...BaseUCMShape,
    type: z.literal("location"),
    content: LocationContent,
  })
  .strict();

export const FlowUCM = z
  .object({
    ...BaseUCMShape,
    type: z.literal("flow"),
    content: FlowContent,
  })
  .strict();

// Composite is recursive — we type it manually with the lazy schema below.
export type UCMMessage =
  | z.infer<typeof TextUCM>
  | z.infer<typeof QuickRepliesUCM>
  | z.infer<typeof ListUCM>
  | z.infer<typeof CtaUrlUCM>
  | z.infer<typeof MediaUCM>
  | z.infer<typeof LocationUCM>
  | z.infer<typeof FlowUCM>
  | CompositeUCMMessage;

export type CompositeUCMMessage = {
  ucm_version: typeof UCM_VERSION;
  message_id: string;
  type: "composite";
  capabilities_required: CapabilityKey[];
  fallback_text: string;
  metadata: Record<string, unknown>;
  content: { children: UCMMessage[] };
};

// Use z.ZodType<UCMMessage, z.ZodTypeDef, unknown> so the input side is
// unknown — that's how Zod recommends typing recursive schemas where the
// input may differ from the output (e.g. defaults).
export const UCMMessageSchema: z.ZodType<UCMMessage, z.ZodTypeDef, unknown> =
  z.lazy(() =>
    z.discriminatedUnion("type", [
      TextUCM,
      QuickRepliesUCM,
      ListUCM,
      CtaUrlUCM,
      MediaUCM,
      LocationUCM,
      FlowUCM,
      CompositeUCM,
    ]),
  );

export const CompositeUCM = z
  .object({
    ...BaseUCMShape,
    type: z.literal("composite"),
    content: z
      .object({
        children: z.array(UCMMessageSchema).min(1).max(20),
      })
      .strict(),
  })
  .strict();

export type UCMType = UCMMessage["type"];

export const UCM_TYPES: readonly UCMType[] = [
  "text",
  "quick_replies",
  "list",
  "cta_url",
  "media",
  "location",
  "flow",
  "composite",
] as const;
