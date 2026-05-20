import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, primaryButton, tokens } from "../tokens";
import type { OnInteractiveResponse } from "../types";

type CtaUrlUCM = Extract<UCMMessage, { type: "cta_url" }>;

/**
 * Renders a UCM ``cta_url`` message — body + a button that opens an
 * external link.
 *
 * Accessibility: the CTA is a real ``<a>`` with ``role="button"`` so
 * screen readers announce both the destination URL (via ``aria-label``)
 * and the call to action. ``rel="noopener noreferrer"`` is set on the
 * outbound link — the operator might be on a corporate browser session.
 *
 * We ALSO fire ``onInteractive`` so the host can record the click
 * server-side (e.g. for QA audit), even though the link itself is what
 * actually navigates. This matches the WhatsApp Flow behaviour where
 * the button press is both an outbound action AND an inbound event.
 */
export function CtaUrl({
  ucm,
  onInteractive,
}: {
  ucm: CtaUrlUCM;
  onInteractive?: OnInteractiveResponse;
}) {
  return (
    <div
      style={bubble}
      data-ucm-type="cta_url"
      data-ucm-message-id={ucm.message_id}
    >
      <div style={{ marginBottom: tokens.spacing }}>{ucm.content.body}</div>
      <a
        href={ucm.content.url}
        role="button"
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`${ucm.content.button_title}: opens ${ucm.content.url} in a new tab`}
        style={{
          ...primaryButton,
          display: "inline-block",
          textDecoration: "none",
        }}
        onClick={() =>
          onInteractive?.({
            id: ucm.message_id,
            title: ucm.content.button_title,
            source: "cta_url",
          })
        }
      >
        {ucm.content.button_title}
      </a>
    </div>
  );
}
