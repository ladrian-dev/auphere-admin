/**
 * JSON Schema export for UCM v1.0.0.
 *
 * Hand-written (instead of generated from Zod) because:
 *   - Zod's discriminated unions of recursive types do not round-trip cleanly
 *     to JSON Schema without extra plumbing.
 *   - The JSON Schema is the cross-language contract; pinning it as data
 *     (not derived) means breaking it requires an explicit, reviewable diff.
 *
 * The two source-of-truth statements (Zod types in TS, Pydantic models in Py)
 * must each produce instances that validate against this schema. The test
 * suite enforces that via fixtures.
 */
export const UCM_JSON_SCHEMA = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "https://nexus.auphere.dev/schemas/ucm/1.0.0/ucm.json",
  title: "UCM v1.0.0",
  description:
    "Universal Channel Message — channel-agnostic message format emitted by Nexus agents.",
  type: "object",
  required: [
    "ucm_version",
    "message_id",
    "type",
    "fallback_text",
    "content",
  ],
  properties: {
    ucm_version: { const: "1.0.0" },
    message_id: { type: "string", minLength: 1, maxLength: 128 },
    type: {
      enum: [
        "text",
        "quick_replies",
        "list",
        "cta_url",
        "media",
        "location",
        "flow",
        "composite",
      ],
    },
    capabilities_required: {
      type: "array",
      items: {
        enum: [
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
        ],
      },
      default: [],
    },
    fallback_text: { type: "string", minLength: 1, maxLength: 4096 },
    metadata: { type: "object", additionalProperties: true, default: {} },
    content: { type: "object" },
  },
  // Discriminator: per-type content validation is enforced by the validators,
  // not by the JSON Schema; doing it here would require allOf+if/then chains
  // that humans can't audit. The schema is the shape contract; the validator
  // is the semantic contract.
  additionalProperties: false,
} as const;

/**
 * Backward-compatibility envelope: when we ship UCM v2.0.0, this module will
 * expose `UCM_JSON_SCHEMA_V1` (current) and `UCM_JSON_SCHEMA_V2` (next), and
 * consumers will pick at the boundary based on `ucm_version`. Until then we
 * only ship v1.
 */
export const SUPPORTED_UCM_VERSIONS: readonly string[] = ["1.0.0"] as const;

export function isSupportedUcmVersion(v: unknown): v is "1.0.0" {
  return typeof v === "string" && SUPPORTED_UCM_VERSIONS.includes(v);
}
