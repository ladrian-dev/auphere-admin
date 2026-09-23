import type { MessageKey } from "@/i18n/messages";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const KNOWN: Record<string, MessageKey> = {
  "channel.message": "meter.channel.message",
  "llm.input_tokens": "meter.llm.input_tokens",
  "llm.output_tokens": "meter.llm.output_tokens",
  "llm.cache_read": "meter.llm.cache_read",
  "llm.cache_write": "meter.llm.cache_write",
  "voice.minutes": "meter.voice.minutes",
};

/**
 * A meter name (``llm.input_tokens``) as the partner should read it. The raw
 * name stays available for a ``title`` so nothing is lost; unknown meters
 * fall back to the raw name rather than to a wrong label.
 */
export function meterLabel(meter: string, t: T): string {
  const known = KNOWN[meter];
  if (known) return t(known);
  if (meter.startsWith("media.")) return t("meter.media", { kind: meter.slice("media.".length) });
  return meter;
}
