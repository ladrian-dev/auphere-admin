import type { UCMMessage } from "@nexus/ucm-schema";

import { CtaUrl } from "./components/CtaUrl";
import { Composite } from "./components/Composite";
import { Flow } from "./components/Flow";
import { List } from "./components/List";
import { Location } from "./components/Location";
import { Media } from "./components/Media";
import { QuickReplies } from "./components/QuickReplies";
import { Text } from "./components/Text";
import { fallbackBox } from "./tokens";
import type { OnInteractiveResponse } from "./types";

/**
 * Renders any UCM v1.0.0 message by dispatching on ``ucm.type``.
 *
 * Unknown types fall back to a yellow box showing the type name and
 * the message's ``fallback_text``. The schema's discriminated union
 * makes this unreachable in normal flow — the fallback exists so a
 * post-1.0 UCM emitted by a newer agent still renders something
 * useful (no crash) until the operator's host is upgraded.
 */
export function UCMRenderer({
  ucm,
  onInteractive,
}: {
  ucm: UCMMessage;
  onInteractive?: OnInteractiveResponse;
}) {
  switch (ucm.type) {
    case "text":
      return <Text ucm={ucm} />;
    case "quick_replies":
      return <QuickReplies ucm={ucm} onInteractive={onInteractive} />;
    case "list":
      return <List ucm={ucm} onInteractive={onInteractive} />;
    case "cta_url":
      return <CtaUrl ucm={ucm} onInteractive={onInteractive} />;
    case "media":
      return <Media ucm={ucm} />;
    case "location":
      return <Location ucm={ucm} />;
    case "flow":
      return <Flow ucm={ucm} onInteractive={onInteractive} />;
    case "composite":
      return (
        <Composite
          ucm={ucm}
          Render={UCMRenderer}
          onInteractive={onInteractive}
        />
      );
    default: {
      // Exhaustive check that yields a runtime fallback for forward
      // compatibility. ``never`` is used so TypeScript fails the build
      // if a new type is added to the schema without a case here.
      const _unknown: never = ucm;
      void _unknown;
      return (
        <div
          style={fallbackBox}
          role="alert"
          aria-label="Unrecognised UCM type"
        >
          Unrecognised UCM type. Fallback: {(ucm as UCMMessage).fallback_text}
        </div>
      );
    }
  }
}
