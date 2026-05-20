/**
 * Shared types for UCM web components.
 *
 * Re-exports the discriminated union from ``@nexus/ucm-schema`` and
 * defines the interaction callback every interactive component takes.
 */
import type { UCMMessage } from "@nexus/ucm-schema";

export type { UCMMessage };

/**
 * Called when the operator clicks a quick-reply, picks a list row,
 * follows a CTA URL, or any other interactive choice. The component
 * passes ``id`` (stable across channels) and ``title`` (what the user
 * saw) so the host can synthesise the right ``interactive_response``
 * event to send back to the agent. See ADR-020.
 */
export type InteractiveResponse = {
  id: string;
  title: string;
  source: "quick_reply" | "list" | "cta_url" | "flow";
};

export type OnInteractiveResponse = (event: InteractiveResponse) => void;

export type UCMComponentProps<T extends UCMMessage = UCMMessage> = {
  ucm: T;
  onInteractive?: OnInteractiveResponse;
};
