/**
 * agendapro_public.check_availability
 *
 * Walks the first two steps of the public booking wizard
 * (cultorbarber.site.agendapro.com/cl/sucursal/<id>):
 *
 *   1. Select service (matches ``service_hint`` fuzzy).
 *   2. Select date (calendar widget; ``on_date``).
 *   3. Read the time-slot grid → slots.
 *
 * No customer data needed; returns slot metadata only. Idempotent and
 * safe to call repeatedly — every call is a fresh Browserbase session.
 *
 * Stagehand v3 API: ``act()`` / ``observe()`` live directly on the
 * Stagehand instance (top-level). Low-level browser ops (goto,
 * screenshot, waitForLoadState) go through the active V3 Page exposed
 * by ``stagehand.context.activePage()``.
 */

import { z } from "zod";

import { logger } from "../lib/logging.js";
import { openSession } from "../lib/stagehand-session.js";

// ── input/output ────────────────────────────────────────────────────────────

export const CheckAvailabilityInput = z.object({
  public_url: z.string().url(),
  on_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  service_hint: z.string().min(1).max(120).optional(),
  duration_hint_min: z.number().int().positive().optional(),
  preferred_barber_name: z.string().max(120).optional(),
});
export type CheckAvailabilityInput = z.infer<typeof CheckAvailabilityInput>;

const SlotSchema = z.object({
  starts_at_iso: z.string(),
  duration_min: z.number().int(),
  barber_name: z.string().nullable(),
  barber_slot_token: z.string(),
});
export const CheckAvailabilityOutput = z.object({
  slots: z.array(SlotSchema),
  recaptcha_score: z.number().nullable(),
  screenshot_url: z.string().optional(),
});
export type CheckAvailabilityOutput = z.infer<typeof CheckAvailabilityOutput>;

// ── flow ────────────────────────────────────────────────────────────────────

export async function checkAvailability(
  input: CheckAvailabilityInput,
): Promise<CheckAvailabilityOutput> {
  const session = await openSession();
  const { stagehand } = session;

  try {
    logger.info(
      { url: input.public_url, on_date: input.on_date },
      "check_availability.start",
    );

    // 1. Navigate.
    const page = stagehand.context.activePage();
    if (!page) {
      throw new Error("stagehand.context.activePage() returned undefined");
    }
    await page.goto(input.public_url, { timeoutMs: 30_000 });

    // 2. Service.
    if (input.service_hint) {
      await stagehand.act(
        `Click on the service named "${input.service_hint}". If multiple match, pick the closest.`,
      );
    }

    // 3. Date picker.
    await stagehand.act(
      `Open the date picker and select ${input.on_date}.`,
    );

    // 4. Wait for slot grid to render.
    await page.waitForLoadState("networkidle", 15_000);

    // 5. Observe slots.
    const observations = await stagehand.observe(
      "List every visible time-slot button on the page. " +
        "For each, include the time text (HH:MM) and any visible " +
        "barber name. Skip disabled/grayed-out buttons.",
    );

    // 6. Parse observations into slot metadata.
    const slots = parseSlots(observations as ObservedAction[], input);
    const screenshot = await captureScreenshotSafe(page);

    logger.info(
      { slot_count: slots.length },
      "check_availability.done",
    );

    return {
      slots,
      recaptcha_score: null, // TODO: scrape window.__recaptchaScore if exposed
      screenshot_url: screenshot,
    };
  } finally {
    await session.close();
  }
}

// ── helpers ─────────────────────────────────────────────────────────────────

// Mirrors the shape Stagehand v3 returns from observe() — duck typed so
// minor SDK shifts don't break the parser.
interface ObservedAction {
  selector?: string;
  description?: string;
  method?: string;
  arguments?: string[];
}

function parseSlots(
  observations: ObservedAction[],
  input: CheckAvailabilityInput,
): Array<{
  starts_at_iso: string;
  duration_min: number;
  barber_name: string | null;
  barber_slot_token: string;
}> {
  const out: Array<{
    starts_at_iso: string;
    duration_min: number;
    barber_name: string | null;
    barber_slot_token: string;
  }> = [];

  for (const obs of observations) {
    const text = (obs.description ?? "").trim();
    if (!text) continue;

    // Expected formats observed at cultorbarber.site.agendapro.com:
    //   "15:00"
    //   "15:00 con Moisés"
    //   "15:00 Moisés (Profesional)"
    const m = text.match(/(\d{1,2}):(\d{2})(?:\s+(?:con\s+)?([^()]+?))?(?:\s*\(|$)/i);
    if (!m) continue;
    const [, hh, mm, rawBarber] = m;
    const hour = Number(hh);
    const minute = Number(mm);
    if (Number.isNaN(hour) || Number.isNaN(minute)) continue;

    // ISO with no timezone; the Python side stamps the tenant TZ.
    const startsAtIso = `${input.on_date}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00`;
    const barberName = rawBarber ? rawBarber.trim() : null;

    // Filter by preferred_barber_name if specified.
    if (
      input.preferred_barber_name &&
      barberName &&
      !barberName.toLowerCase().includes(input.preferred_barber_name.toLowerCase())
    ) {
      continue;
    }

    out.push({
      starts_at_iso: startsAtIso,
      duration_min: input.duration_hint_min ?? 30,
      barber_name: barberName,
      // Use the observed selector as the slot token. It is opaque to
      // the agent and only meaningful to create_appointment.
      barber_slot_token: obs.selector ?? `text:${text}`,
    });
  }

  return out;
}

async function captureScreenshotSafe(
  page: { screenshot: (opts?: object) => Promise<Buffer> },
): Promise<string | undefined> {
  try {
    // Phase 1: data: URL truncated marker. Phase 2: upload to S3 via
    // Python side and return the s3 key instead.
    const buffer = await page.screenshot();
    return `data:image/png;base64,${buffer.toString("base64").slice(0, 24)}...truncated`;
  } catch (e) {
    logger.warn({ err: e }, "screenshot.failed");
    return undefined;
  }
}
