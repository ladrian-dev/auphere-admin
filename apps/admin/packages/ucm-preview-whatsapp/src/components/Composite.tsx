import type { UCMMessage } from "@nexus/ucm-schema";

import { wa } from "../tokens";

type CompositeUCM = Extract<UCMMessage, { type: "composite" }>;

/**
 * WhatsApp Cloud API doesn't have a native "composite" — each UCM
 * child becomes its own message. The preview stacks them vertically
 * to show how the operator's screen would scroll after the agent's
 * turn. ``Render`` is injected to avoid the circular import (same
 * pattern as ``ucm-render-web``).
 */
export function Composite({
  ucm,
  Render,
}: {
  ucm: CompositeUCM;
  Render: (props: { ucm: UCMMessage }) => React.ReactNode;
}) {
  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: wa.spacing }}
      data-wa-type="composite"
      data-ucm-message-id={ucm.message_id}
    >
      {ucm.content.children.map((child) => (
        <Render key={child.message_id} ucm={child} />
      ))}
    </div>
  );
}
