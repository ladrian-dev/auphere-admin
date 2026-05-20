import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, meta, wa } from "../tokens";

type ListUCM = Extract<UCMMessage, { type: "list" }>;

/**
 * WhatsApp interactive `list` message — body + one button that opens
 * a bottom-sheet picker. The preview collapses the picker inline so
 * the operator can see the row contents at a glance without simulating
 * the modal.
 */
export function List({ ucm }: { ucm: ListUCM }) {
  return (
    <div
      style={{ ...bubble, padding: 0 }}
      data-wa-type="list"
      data-ucm-message-id={ucm.message_id}
    >
      <div style={{ padding: "8px 10px 6px" }}>
        {ucm.content.header && (
          <div
            style={{
              fontWeight: 700,
              fontSize: 13,
              color: wa.textMuted,
              marginBottom: 4,
            }}
          >
            {ucm.content.header}
          </div>
        )}
        <div>{ucm.content.body}</div>
        {ucm.content.footer && (
          <div
            style={{ fontSize: 12, color: wa.textMuted, marginTop: 4 }}
          >
            {ucm.content.footer}
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
          padding: 8,
          textAlign: "center",
          color: wa.link,
          fontWeight: 500,
        }}
      >
        ☰ {ucm.content.button_text}
      </div>
      <div style={{ background: wa.surface, padding: "6px 10px 10px" }}>
        {ucm.content.sections.map((section, si) => (
          <div key={`s${si}`} style={{ marginTop: si === 0 ? 0 : 8 }}>
            <div
              style={{
                fontSize: 11,
                color: wa.textMuted,
                textTransform: "uppercase",
                letterSpacing: 0.4,
                marginBottom: 4,
              }}
            >
              {section.title}
            </div>
            {section.rows.map((row) => (
              <div
                key={row.id}
                style={{
                  padding: "6px 0",
                  borderBottom: `1px solid ${wa.divider}`,
                }}
              >
                <div style={{ fontWeight: 500 }}>{row.title}</div>
                {row.description && (
                  <div style={{ fontSize: 12, color: wa.textMuted }}>
                    {row.description}
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
