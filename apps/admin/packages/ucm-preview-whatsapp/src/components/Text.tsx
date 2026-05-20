import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, meta } from "../tokens";

type TextUCM = Extract<UCMMessage, { type: "text" }>;

/**
 * WhatsApp Cloud API renders the body verbatim. Markdown is NOT
 * Cloud-API-native; the closest WhatsApp does is its in-app
 * ``*bold* _italic_ ~strike~`` micro-formatting which we deliberately
 * skip rendering here — the preview shows what the operator's eyes
 * would see, which includes the raw asterisks if the agent emits them.
 */
export function Text({ ucm }: { ucm: TextUCM }) {
  return (
    <div style={bubble} data-wa-type="text" data-ucm-message-id={ucm.message_id}>
      <div style={{ whiteSpace: "pre-wrap" }}>{ucm.content.body}</div>
      <div style={meta} aria-hidden="true">
        14:32 ✓✓
      </div>
    </div>
  );
}
