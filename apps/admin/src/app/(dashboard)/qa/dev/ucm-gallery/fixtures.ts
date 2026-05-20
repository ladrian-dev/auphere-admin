/**
 * Gallery fixture loader.
 *
 * Imports the vendored JSON inside ``@nexus/ucm-schema`` via Next.js's
 * native JSON import (``resolveJsonModule: true``). The bundler embeds
 * the JSON in the build output, so this works in dev, in production,
 * and in Vercel's container — no runtime fs.readFileSync needed.
 *
 * Each entry is parsed through Zod so a malformed fixture fails the
 * build, not the runtime render.
 */
import rawFixtures from "@/../packages/ucm-schema/__fixtures__/valid.json";

import { UCMMessageSchema, type UCMMessage } from "@nexus/ucm-schema";

const LABELS: Record<string, string> = {
  text_plain: "Plain text",
  text_markdown: "Text with markdown body",
  quick_replies_3: "Quick replies (3 buttons — fits WhatsApp)",
  quick_replies_5: "Quick replies (5 buttons — WhatsApp truncates to 3)",
  list_small: "List (one section, 3 rows)",
  cta_url: "Call-to-action URL",
  media_image: "Media — image with caption",
  location: "Location",
  flow: "WhatsApp flow",
  composite: "Composite (text + quick replies)",
};

const ORDER = [
  "text_plain",
  "text_markdown",
  "quick_replies_3",
  "quick_replies_5",
  "list_small",
  "cta_url",
  "media_image",
  "location",
  "flow",
  "composite",
] as const;

export const UCM_GALLERY_FIXTURES: Array<{
  key: string;
  label: string;
  ucm: UCMMessage;
}> = ORDER.filter((k) => k in rawFixtures).map((k) => ({
  key: k,
  label: LABELS[k] ?? k,
  ucm: UCMMessageSchema.parse(rawFixtures[k]),
}));
