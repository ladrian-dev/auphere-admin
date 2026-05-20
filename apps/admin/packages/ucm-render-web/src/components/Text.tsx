import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble } from "../tokens";

type TextUCM = Extract<UCMMessage, { type: "text" }>;

/**
 * Renders a UCM ``text`` message.
 *
 * Markdown is rendered as plain text (no parsing) by design: the QA
 * Playground stays predictable, and the agent's intent is preserved in
 * the schema. If the host wants markdown the renderer can be swapped
 * out via the component registry — see ``UCMRenderer``.
 */
export function Text({ ucm }: { ucm: TextUCM }) {
  return (
    <div
      style={{ ...bubble, whiteSpace: "pre-wrap" }}
      role="article"
      aria-label="agent message"
      data-ucm-type="text"
      data-ucm-message-id={ucm.message_id}
    >
      {ucm.content.body}
    </div>
  );
}
