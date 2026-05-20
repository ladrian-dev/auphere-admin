import type { UCMMessage } from "@nexus/ucm-schema";

import { Composite } from "./components/Composite";
import { CtaUrl } from "./components/CtaUrl";
import { Flow } from "./components/Flow";
import { List } from "./components/List";
import { Location } from "./components/Location";
import { Media } from "./components/Media";
import { QuickReplies } from "./components/QuickReplies";
import { Text } from "./components/Text";
import { phoneFrame } from "./tokens";

/**
 * Renders any UCM v1.0.0 as a WhatsApp Cloud API chat bubble.
 *
 * Always wraps the bubble in a "phone frame" container so the operator
 * sees the message in context — bubble width, chat background, etc. —
 * instead of a card floating on a white page. The frame is part of
 * the preview's identity ("this is what WhatsApp would show").
 */
export function WhatsAppPreview({ ucm }: { ucm: UCMMessage }) {
  return (
    <div style={phoneFrame} data-wa-preview-root>
      <WhatsAppRenderer ucm={ucm} />
    </div>
  );
}

/** Same as above but without the phone frame — handy for embedding. */
export function WhatsAppRenderer({ ucm }: { ucm: UCMMessage }) {
  switch (ucm.type) {
    case "text":
      return <Text ucm={ucm} />;
    case "quick_replies":
      return <QuickReplies ucm={ucm} />;
    case "list":
      return <List ucm={ucm} />;
    case "cta_url":
      return <CtaUrl ucm={ucm} />;
    case "media":
      return <Media ucm={ucm} />;
    case "location":
      return <Location ucm={ucm} />;
    case "flow":
      return <Flow ucm={ucm} />;
    case "composite":
      return <Composite ucm={ucm} Render={WhatsAppRenderer} />;
    default: {
      const _unknown: never = ucm;
      void _unknown;
      return (
        <div role="alert">
          Unrecognised UCM type. Fallback: {(ucm as UCMMessage).fallback_text}
        </div>
      );
    }
  }
}
