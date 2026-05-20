import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, meta, wa } from "../tokens";

type LocationUCM = Extract<UCMMessage, { type: "location" }>;

/**
 * WhatsApp location bubble — a stylised map tile placeholder + the
 * name / address below. We never render an actual map tile (no API
 * key, no network leak from the QA sandbox).
 */
export function Location({ ucm }: { ucm: LocationUCM }) {
  const { latitude, longitude, name, address } = ucm.content;
  return (
    <div
      style={{ ...bubble, padding: 0 }}
      data-wa-type="location"
      data-ucm-message-id={ucm.message_id}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #c7e9c0 0%, #8fc89a 100%)",
          height: 120,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 36,
          color: wa.text,
          borderTopLeftRadius: wa.radius,
          borderTopRightRadius: wa.radius,
        }}
        aria-label="Map preview"
      >
        📍
      </div>
      <div style={{ padding: "8px 10px 6px" }}>
        {name && (
          <div style={{ fontWeight: 600 }}>{name}</div>
        )}
        {address && (
          <div style={{ fontSize: 13, color: wa.textMuted }}>{address}</div>
        )}
        <div
          style={{
            fontSize: 11,
            color: wa.textMuted,
            marginTop: 2,
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {latitude.toFixed(4)}, {longitude.toFixed(4)}
        </div>
        <div style={meta} aria-hidden="true">
          14:32 ✓✓
        </div>
      </div>
    </div>
  );
}
