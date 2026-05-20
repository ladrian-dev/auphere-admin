import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, button, meta, wa } from "../tokens";

type CtaUrlUCM = Extract<UCMMessage, { type: "cta_url" }>;

export function CtaUrl({ ucm }: { ucm: CtaUrlUCM }) {
  return (
    <div
      style={{ ...bubble, padding: 0 }}
      data-wa-type="cta_url"
      data-ucm-message-id={ucm.message_id}
    >
      <div style={{ padding: "8px 10px 6px" }}>
        <div>{ucm.content.body}</div>
        <div style={meta} aria-hidden="true">
          14:32 ✓✓
        </div>
      </div>
      <div
        style={{
          background: wa.surface,
          borderRadius: wa.radius,
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
          aria-label={`CTA URL: ${ucm.content.url}`}
        >
          🔗 {ucm.content.button_title}
        </div>
      </div>
    </div>
  );
}
