import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, meta, wa } from "../tokens";

type MediaUCM = Extract<UCMMessage, { type: "media" }>;

/**
 * WhatsApp Cloud API media bubble — the media itself + an optional
 * caption. WhatsApp shows a small file-size + duration overlay for
 * video/audio; we omit that because we don't have those numbers in
 * the UCM payload.
 */
export function Media({ ucm }: { ucm: MediaUCM }) {
  const { kind, url, caption, filename } = ucm.content;
  const alt = caption ?? ucm.fallback_text;

  let media: React.ReactNode;
  if (kind === "image") {
    media = (
      <img
        src={url}
        alt={alt}
        style={{
          width: "100%",
          borderTopLeftRadius: wa.radius,
          borderTopRightRadius: wa.radius,
          display: "block",
        }}
      />
    );
  } else if (kind === "video") {
    media = (
      <div
        style={{
          background: "#000",
          color: "#fff",
          padding: 24,
          textAlign: "center",
          borderTopLeftRadius: wa.radius,
          borderTopRightRadius: wa.radius,
        }}
        aria-label={`Video: ${alt}`}
      >
        ▶ Video
      </div>
    );
  } else if (kind === "audio") {
    media = (
      <div
        style={{
          background: wa.surface,
          padding: "10px 12px",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
        aria-label={`Audio: ${alt}`}
      >
        ▶ ▬▬▬▬▬▬▬▬▬
        <span style={{ color: wa.textMuted, fontSize: 12 }}>0:00</span>
      </div>
    );
  } else {
    // document
    media = (
      <div
        style={{
          background: wa.surface,
          padding: "10px 12px",
          display: "flex",
          alignItems: "center",
          gap: 8,
          color: wa.text,
        }}
        aria-label={`Document: ${filename ?? url}`}
      >
        📄 <strong>{filename ?? "document.pdf"}</strong>
      </div>
    );
  }

  return (
    <div
      style={{ ...bubble, padding: 0 }}
      data-wa-type="media"
      data-wa-media-kind={kind}
      data-ucm-message-id={ucm.message_id}
    >
      {media}
      {caption && (
        <div style={{ padding: "6px 10px 4px" }}>
          {caption}
        </div>
      )}
      <div style={{ ...meta, padding: "0 10px 6px" }} aria-hidden="true">
        14:32 ✓✓
      </div>
    </div>
  );
}
