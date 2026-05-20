import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, primaryButton, tokens } from "../tokens";
import type { OnInteractiveResponse } from "../types";

type FlowUCM = Extract<UCMMessage, { type: "flow" }>;

/**
 * Renders a UCM ``flow`` message — the entrypoint to a WhatsApp Flow.
 *
 * In QA we don't actually launch the Flow's webview (no Cloud API
 * registration on sandbox), so the button surfaces the flow_id +
 * screen so the operator can verify the agent picked the right one.
 * Clicking the button fires ``onInteractive`` with the flow_id as
 * ``id``; the host (Playground) can synthesise a Flow completion to
 * keep the conversation going if the test demands it.
 */
export function Flow({
  ucm,
  onInteractive,
}: {
  ucm: FlowUCM;
  onInteractive?: OnInteractiveResponse;
}) {
  const c = ucm.content;
  return (
    <div
      style={bubble}
      data-ucm-type="flow"
      data-ucm-message-id={ucm.message_id}
      data-ucm-flow-id={c.flow_id}
    >
      {c.header_text && (
        <div
          style={{
            fontWeight: 600,
            fontSize: 12,
            color: tokens.textMuted,
            textTransform: "uppercase",
            letterSpacing: 0.5,
            marginBottom: tokens.spacing / 2,
          }}
        >
          {c.header_text}
        </div>
      )}
      {c.body && <div style={{ marginBottom: tokens.spacing }}>{c.body}</div>}
      <button
        type="button"
        aria-label={`Open WhatsApp flow ${c.flow_id}${
          c.screen ? ` at screen ${c.screen}` : ""
        }`}
        style={primaryButton}
        onClick={() =>
          onInteractive?.({
            id: c.flow_id,
            title: c.button_text,
            source: "flow",
          })
        }
      >
        {c.button_text}
      </button>
      {c.footer_text && (
        <div
          style={{
            marginTop: tokens.spacing,
            fontSize: 12,
            color: tokens.textMuted,
          }}
        >
          {c.footer_text}
        </div>
      )}
      <div
        style={{
          marginTop: tokens.spacing,
          fontSize: 11,
          color: tokens.textMuted,
          fontFamily: "ui-monospace, SFMono-Regular, monospace",
        }}
        aria-hidden="true"
      >
        flow_id: {c.flow_id}
        {c.screen ? ` · screen: ${c.screen}` : ""}
      </div>
    </div>
  );
}
