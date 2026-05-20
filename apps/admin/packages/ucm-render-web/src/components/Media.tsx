import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, tokens } from "../tokens";

type MediaUCM = Extract<UCMMessage, { type: "media" }>;

/**
 * Renders a UCM ``media`` message.
 *
 * Type-aware: ``image`` shows ``<img>``, ``video`` shows ``<video controls>``,
 * ``audio`` shows ``<audio controls>``, ``document`` shows a download link
 * with the filename when available. Every variant exposes the caption
 * as text below the media so screen-reader-only operators get the
 * same information as sighted ones.
 *
 * ``alt`` on images is ``caption || fallback_text`` — the schema
 * guarantees ``fallback_text`` is non-empty.
 */
export function Media({ ucm }: { ucm: MediaUCM }) {
  const { kind, url, caption, filename } = ucm.content;
  const alt = caption ?? ucm.fallback_text;

  let media: React.ReactNode = null;
  if (kind === "image") {
    media = (
      <img
        src={url}
        alt={alt}
        style={{
          maxWidth: "100%",
          borderRadius: tokens.radiusSm,
          display: "block",
        }}
      />
    );
  } else if (kind === "video") {
    media = (
      <video
        controls
        src={url}
        aria-label={alt}
        style={{ maxWidth: "100%", borderRadius: tokens.radiusSm }}
      />
    );
  } else if (kind === "audio") {
    media = <audio controls src={url} aria-label={alt} />;
  } else {
    // document
    media = (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        download={filename ?? undefined}
        aria-label={`Open document: ${filename ?? url}`}
        style={{
          display: "inline-block",
          padding: `${tokens.spacing}px ${tokens.spacing * 1.25}px`,
          background: tokens.surfaceMuted,
          border: `1px solid ${tokens.border}`,
          borderRadius: tokens.radiusSm,
          color: tokens.text,
          textDecoration: "none",
        }}
      >
        📄 {filename ?? "Document"}
      </a>
    );
  }

  return (
    <div
      style={bubble}
      data-ucm-type="media"
      data-ucm-media-kind={kind}
      data-ucm-message-id={ucm.message_id}
    >
      {media}
      {caption && (
        <div
          style={{
            marginTop: tokens.spacing,
            color: tokens.textMuted,
            fontSize: 13,
          }}
        >
          {caption}
        </div>
      )}
    </div>
  );
}
