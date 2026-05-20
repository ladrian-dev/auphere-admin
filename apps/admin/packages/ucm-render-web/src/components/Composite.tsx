import type { UCMMessage } from "@nexus/ucm-schema";

import { tokens } from "../tokens";
import type { OnInteractiveResponse } from "../types";

type CompositeUCM = Extract<UCMMessage, { type: "composite" }>;

/**
 * Renders a UCM ``composite`` message — an ordered group of children.
 *
 * Renders children stacked with a small gap. The host (UCMRenderer)
 * recurses naturally because composite passes each child back through
 * the dispatcher.
 *
 * Forward declaration: ``UCMRenderer`` is passed in as a prop to avoid
 * a circular dependency between this file and the dispatcher.
 */
export function Composite({
  ucm,
  Render,
  onInteractive,
}: {
  ucm: CompositeUCM;
  Render: (props: { ucm: UCMMessage; onInteractive?: OnInteractiveResponse }) => React.ReactNode;
  onInteractive?: OnInteractiveResponse;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: tokens.spacing,
      }}
      data-ucm-type="composite"
      data-ucm-message-id={ucm.message_id}
    >
      {ucm.content.children.map((child) => (
        <Render
          key={child.message_id}
          ucm={child}
          onInteractive={onInteractive}
        />
      ))}
    </div>
  );
}
