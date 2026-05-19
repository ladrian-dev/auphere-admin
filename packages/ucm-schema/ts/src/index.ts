/**
 * Public API of `@nexus/ucm-schema`.
 *
 * Cheat sheet:
 *   import { UCMMessageSchema, UCM_VERSION } from "@nexus/ucm-schema";
 *   import { validate } from "@nexus/ucm-schema";
 *   import { degrade } from "@nexus/ucm-schema";
 *   import { CHANNELS, getChannel } from "@nexus/ucm-schema";
 */
export {
  UCM_VERSION,
  UCM_TYPES,
  UCMMessageSchema,
  TextUCM,
  QuickRepliesUCM,
  ListUCM,
  CtaUrlUCM,
  MediaUCM,
  LocationUCM,
  FlowUCM,
  CompositeUCM,
  type UCMMessage,
  type CompositeUCMMessage,
  type UCMType,
  type CapabilityKey,
  type MediaKind,
} from "./types.js";

export {
  CHANNELS,
  WEB,
  WHATSAPP,
  INSTAGRAM,
  MESSENGER,
  VOICE,
  getChannel,
  channelSupports,
  inferCapabilities,
  type ChannelName,
  type ChannelProfile,
  type ChannelLimits,
} from "./channels/capabilities.js";

export {
  validate,
  type ValidationIssue,
  type ValidationResult,
} from "./validators/index.js";

export {
  degrade,
  type DegradationStep,
  type DegradeResult,
} from "./degrade.js";

export {
  UCM_JSON_SCHEMA,
  SUPPORTED_UCM_VERSIONS,
  isSupportedUcmVersion,
} from "./json-schema.js";
