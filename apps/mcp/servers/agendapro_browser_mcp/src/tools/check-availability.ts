/**
 * agendapro.check_availability — read-only, cache 5min Redis.
 *
 * Stagehand reside en el calendar/booking page del barbero (o "any
 * barber"), parsea slots disponibles en el día, devuelve.
 *
 * Phase 1 implementation: pragmatic. AgendaPro's calendar UI difiere
 * por business config, así que usamos ``act()`` + ``extract()`` con
 * Zod schema para que el LLM-fallback recoja slots robustamente.
 *
 * Slot shape esperado: ``{ starts_at, ends_at, barber_external_id }``.
 * Si el LLM no encuentra slots o la página falla, se devuelve lista
 * vacía con ``cached=false``. El caller (booking-server) puede caer al
 * camino local Bloque D si hace falta.
 */

import { z } from 'zod';

import type { AvailabilityCache } from '../cache.js';
import { log } from '../logging.js';
import {
  type AgendaProSlot,
  type CheckAvailabilityOutput,
  CheckAvailabilityInputSchema,
} from '../schemas.js';
import { pageOf } from '../stagehand/page.js';
import type { BrowserSession } from '../stagehand/session.js';

const SLOT_EXTRACT_SCHEMA = z.object({
  slots: z.array(
    z.object({
      starts_at: z.string(),
      ends_at: z.string(),
      barber_external_id: z.string().nullable(),
    }),
  ),
});

export async function checkAvailability(
  rawArgs: unknown,
  ctx: { session: BrowserSession; cache: AvailabilityCache; agendaproBaseUrl: string },
): Promise<CheckAvailabilityOutput> {
  const args = CheckAvailabilityInputSchema.parse(rawArgs);
  const cacheKey = {
    barber: args.barber_external_id ?? null,
    date: args.on_date,
    service: args.service_name,
  };

  const cached = await ctx.cache.get<AgendaProSlot[]>(cacheKey);
  if (cached !== null) {
    log.info({ key: cacheKey }, 'check_availability.cache_hit');
    return {
      on_date: args.on_date,
      service_name: args.service_name,
      slots: cached,
      cached: true,
      session: { needs_reauth: false },
    };
  }

  if (!args.context_id) {
    throw new Error('context_id is required for check_availability — bootstrap first');
  }
  await ctx.session.ensureAttached(args.context_id);
  const sh = ctx.session.stagehand();
  const page = await pageOf(sh);

  // Navigate to the booking calendar.
  const calendarUrl = `${ctx.agendaproBaseUrl}/cl/dashboard/agenda?date=${args.on_date}`;
  await page.goto(calendarUrl, { waitUntil: 'networkidle' });

  if (await ctx.session.detectExpired()) {
    return {
      on_date: args.on_date,
      service_name: args.service_name,
      slots: [],
      cached: false,
      session: { needs_reauth: true },
    };
  }

  // If a specific barber requested, filter the view.
  if (args.barber_external_id) {
    await sh.act(
      `Filter the calendar to show only the professional with id ${args.barber_external_id}`,
    );
  }

  const extracted = await sh.extract(
    `List all available time slots on ${args.on_date} for service "${args.service_name}" with duration ${args.duration_min} minutes. Return ISO datetimes for starts_at and ends_at.`,
    SLOT_EXTRACT_SCHEMA,
  );

  const slots: AgendaProSlot[] = (extracted.slots ?? []).map((s) => ({
    starts_at: s.starts_at,
    ends_at: s.ends_at,
    barber_external_id: s.barber_external_id ?? args.barber_external_id ?? null,
  }));
  await ctx.cache.set(cacheKey, slots);
  log.info({ count: slots.length, key: cacheKey }, 'check_availability.fetched');
  return {
    on_date: args.on_date,
    service_name: args.service_name,
    slots,
    cached: false,
    session: { needs_reauth: false },
  };
}
