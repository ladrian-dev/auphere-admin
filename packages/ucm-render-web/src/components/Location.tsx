import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, tokens } from "../tokens";

type LocationUCM = Extract<UCMMessage, { type: "location" }>;

/**
 * Renders a UCM ``location`` message.
 *
 * In the QA Playground we never load Google Maps tiles — operator
 * sessions stay sandboxed and the agent doesn't need a real map to
 * verify it picked the right coordinates. We show:
 *   - Name (if provided) as the header,
 *   - Address (if provided) below,
 *   - Lat/lon coordinates as text,
 *   - A button that opens the coordinates in the OS map app via the
 *     ``geo:`` URI scheme (no JS, no third-party SDK).
 */
export function Location({ ucm }: { ucm: LocationUCM }) {
  const { latitude, longitude, name, address } = ucm.content;
  const geoHref = `geo:${latitude},${longitude}`;

  return (
    <div
      style={bubble}
      data-ucm-type="location"
      data-ucm-message-id={ucm.message_id}
      role="article"
      aria-label="location"
    >
      {name && (
        <div style={{ fontWeight: 600, marginBottom: tokens.spacing / 2 }}>
          {name}
        </div>
      )}
      {address && (
        <div style={{ color: tokens.textMuted, marginBottom: tokens.spacing / 2 }}>
          {address}
        </div>
      )}
      <div
        style={{
          fontFamily: "ui-monospace, SFMono-Regular, monospace",
          fontSize: 13,
          color: tokens.textMuted,
        }}
      >
        {latitude.toFixed(6)}, {longitude.toFixed(6)}
      </div>
      <a
        href={geoHref}
        aria-label={`Open ${name ?? "location"} in maps`}
        style={{
          display: "inline-block",
          marginTop: tokens.spacing,
          color: tokens.accent,
          textDecoration: "none",
        }}
      >
        📍 Open in maps
      </a>
    </div>
  );
}
