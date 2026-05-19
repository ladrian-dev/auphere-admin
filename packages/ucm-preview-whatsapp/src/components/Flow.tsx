import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, button, meta, wa } from "../tokens";

type FlowUCM = Extract<UCMMessage, { type: "flow" }>;

/**
 * WhatsApp Flow bubble. Visually similar to ``cta_url`` because that's
 * how Cloud API renders it: header + body + a single button that opens
 * the Flow webview. The flow_id stays in a small footer for debug.
 */
export function Flow({ ucm }: { ucm: FlowUCM }) {
  const c = ucm.content;
  return (
    <div
      style={{ ...bubble, padding: 0 }}
      data-wa-type="flow"
      data-ucm-message-id={ucm.message_id}
      data-ucm-flow-id={c.flow_id}
    >
      <div style={{ padding: "8px 10px 6px" }}>
        {c.header_text && (
          <div
            style={{
              fontSize: 11,
              color: wa.textMuted,
              textTransform: "uppercase",
              letterSpacing: 0.4,
              marginBottom: 4,
            }}
          >
            {c.header_text}
          </div>
        )}
        {c.body && <div>{c.body}</div>}
        {c.footer_text && (
          <div style={{ fontSize: 12, color: wa.textMuted, marginTop: 4 }}>
            {c.footer_text}
          </div>
        )}
        <div style={meta} aria-hidden="true">
          14:32 ✓✓
        </div>
      </div>
      <div
        style={{
          background: wa.surface,
          borderTop: `1px solid ${wa.divider}`,
        }}
      >
        <div
          style={{
            ...button,
            color: wa.link,
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            gap: 6,
          }}
          aria-label={`Open Flow ${c.flow_id}`}
        >
          ⏩ {c.button_text}
        </div>
      </div>
    </div>
  );
}
