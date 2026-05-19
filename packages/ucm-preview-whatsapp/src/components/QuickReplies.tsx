import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, button, meta, wa } from "../tokens";

type QuickRepliesUCM = Extract<UCMMessage, { type: "quick_replies" }>;

/**
 * WhatsApp interactive `button` message — body + up to 3 inline reply
 * buttons stacked below the body, separated by a thin divider.
 *
 * Buttons here are STATIC (no onClick). The preview's job is to show
 * the operator what the customer would see; the real interaction lives
 * in the web channel renderer.
 */
export function QuickReplies({ ucm }: { ucm: QuickRepliesUCM }) {
  return (
    <div
      style={{ ...bubble, padding: 0 }}
      data-wa-type="quick_replies"
      data-ucm-message-id={ucm.message_id}
    >
      <div style={{ padding: "8px 10px 6px" }}>
        <div>{ucm.content.body}</div>
        <div style={meta} aria-hidden="true">
          14:32 ✓✓
        </div>
      </div>
      <div style={{ background: wa.surface, borderRadius: wa.radius }}>
        {ucm.content.buttons.slice(0, 3).map((btn) => (
          <div key={btn.id} style={button} aria-label={`Reply button: ${btn.title}`}>
            {btn.title}
          </div>
        ))}
        {ucm.content.buttons.length > 3 && (
          <div
            style={{ ...button, fontStyle: "italic", color: wa.textMuted }}
            aria-label="Truncation notice"
          >
            +{ucm.content.buttons.length - 3} more (WhatsApp caps at 3)
          </div>
        )}
      </div>
    </div>
  );
}
