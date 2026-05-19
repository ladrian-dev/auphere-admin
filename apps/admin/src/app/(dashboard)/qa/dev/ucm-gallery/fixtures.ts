/**
 * Gallery fixture loader.
 *
 * Reads ``packages/ucm-schema/fixtures/valid.json`` at module load time
 * via Node's fs (this file is only imported from a server component, so
 * fs access is safe). Each entry is parsed through Zod so a malformed
 * fixture fails the build, not the runtime render.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { UCMMessageSchema, type UCMMessage } from "@nexus/ucm-schema";

const here = dirname(fileURLToPath(import.meta.url));
// admin/src/app/(dashboard)/qa/_dev/ucm-gallery → repo/packages/ucm-schema/fixtures
const FIXTURES_PATH = resolve(
  here,
  "../../../../../../../../packages/ucm-schema/fixtures/valid.json",
);

const rawFixtures = JSON.parse(readFileSync(FIXTURES_PATH, "utf-8")) as Record<
  string,
  unknown
>;

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
