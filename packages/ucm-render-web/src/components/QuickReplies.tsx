import type { KeyboardEvent } from "react";

import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, button, tokens } from "../tokens";
import type { OnInteractiveResponse } from "../types";

type QuickRepliesUCM = Extract<UCMMessage, { type: "quick_replies" }>;

/**
 * Renders a UCM ``quick_replies`` message — body + up to 10 buttons.
 *
 * Accessibility: the buttons live in a ``role="group"`` labelled by the
 * body text so screen readers announce them as a single choice set.
 * Each button has an explicit ``aria-label`` (button.title), and the
 * group supports arrow-key navigation on top of the default Tab
 * behaviour.
 */
export function QuickReplies({
  ucm,
  onInteractive,
}: {
  ucm: QuickRepliesUCM;
  onInteractive?: OnInteractiveResponse;
}) {
  const labelId = `qr-${ucm.message_id}-label`;

  function handleKeyDown(e: KeyboardEvent<HTMLButtonElement>, idx: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const group = e.currentTarget.parentElement;
    if (!group) return;
    const buttons = Array.from(
      group.querySelectorAll<HTMLButtonElement>("button[data-qr-btn]"),
    );
    const next =
      e.key === "ArrowRight"
        ? (idx + 1) % buttons.length
        : (idx - 1 + buttons.length) % buttons.length;
    buttons[next]?.focus();
  }

  return (
    <div
      style={bubble}
      data-ucm-type="quick_replies"
      data-ucm-message-id={ucm.message_id}
    >
      <div id={labelId} style={{ marginBottom: tokens.spacing }}>
        {ucm.content.body}
      </div>
      <div
        role="group"
        aria-labelledby={labelId}
        style={{
          display: "flex",
          gap: tokens.spacing,
          flexWrap: "wrap",
        }}
      >
        {ucm.content.buttons.map((btn, idx) => (
          <button
            key={btn.id}
            type="button"
            data-qr-btn
            aria-label={btn.title}
            style={button}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            onClick={() =>
              onInteractive?.({
                id: btn.id,
                title: btn.title,
                source: "quick_reply",
              })
            }
          >
            {btn.title}
          </button>
        ))}
      </div>
    </div>
  );
}
