/**
 * agendapro.scrape_no_shows — cron 22:00 tenant TZ (Bloque H).
 *
 * Identifica las citas del día con status=no_show. AgendaPro suele
 * marcar las citas como no_show automáticamente o a mano por el staff.
 * Si la barbería no marca, este endpoint heurísticamente identifica:
 * appointments con starts_at < now() - 30min sin status='completed' ni
 * 'cancelled'.
 */

import { z } from 'zod';

import type { ServerConfig } from '../config.js';
import { NoShowEntrySchema } from '../schemas.js';
import {
  type ScrapeNoShowsOutput,
  ScrapeNoShowsInputSchema,
} from '../schemas.js';
import type { ScreenshotStore } from '../screenshot-store.js';
import type { BrowserSession } from '../stagehand/session.js';
import { _internalCaptureScreenshot } from './create-appointment.js';

const NO_SHOWS_SCHEMA = z.object({
  no_shows: z.array(NoShowEntrySchema),
});

export async function scrapeNoShows(
  rawArgs: unknown,
  ctx: {
    session: BrowserSession;
    screenshotStore: ScreenshotStore;
    config: ServerConfig;
  },
): Promise<ScrapeNoShowsOutput> {
  const args = ScrapeNoShowsInputSchema.parse(rawArgs);
  const onDate = args.on_date ?? new Date().toISOString().slice(0, 10);
  if (!args.context_id) {
    throw new Error('context_id is required for scrape_no_shows');
  }
  await ctx.session.ensureAttached(args.context_id);
  const sh = ctx.session.stagehand();
  await sh.page.goto(
    `${ctx.config.agendaproBaseUrl}/cl/dashboard/agenda?date=${onDate}`,
    { waitUntil: 'networkidle' },
  );
  if (await ctx.session.detectExpired()) {
    return {
      on_date: onDate,
      no_shows: [],
      screenshot: { screenshot_url: null, screenshot_failed: true, screenshot_error: 'session_expired' },
      session: { needs_reauth: true },
    };
  }

  const extracted = await sh.page.extract({
    instruction: `On the calendar for ${onDate}, list every appointment whose starts_at has already passed AND whose status is "no_show", "no llegó", or appears as a missed appointment. Return external_ref, starts_at (ISO), service_name, customer_name, customer_phone, barber_external_id. Use null for missing fields.`,
    schema: NO_SHOWS_SCHEMA,
  });
  const screenshot = await _internalCaptureScreenshot(ctx, args.context_id);
  return {
    on_date: onDate,
    no_shows: extracted.no_shows ?? [],
    screenshot,
    session: { needs_reauth: false },
  };
}
