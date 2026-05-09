/**
 * agendapro.get_today_appointments — read-only.
 *
 * Vista del calendario del día. Stagehand extract con Zod.
 */

import { z } from 'zod';

import type { ServerConfig } from '../config.js';
import { AgendaProAppointmentSchema } from '../schemas.js';
import {
  type GetTodayAppointmentsOutput,
  GetTodayAppointmentsInputSchema,
} from '../schemas.js';
import { pageOf } from '../stagehand/page.js';
import type { BrowserSession } from '../stagehand/session.js';

const TODAY_SCHEMA = z.object({
  appointments: z.array(AgendaProAppointmentSchema),
});

export async function getTodayAppointments(
  rawArgs: unknown,
  ctx: { session: BrowserSession; config: ServerConfig },
): Promise<GetTodayAppointmentsOutput> {
  const args = GetTodayAppointmentsInputSchema.parse(rawArgs);
  if (!args.context_id) {
    throw new Error('context_id is required for get_today_appointments');
  }
  await ctx.session.ensureAttached(args.context_id);
  const sh = ctx.session.stagehand();
  const page = await pageOf(sh);
  const today = new Date().toISOString().slice(0, 10);
  await page.goto(
    `${ctx.config.agendaproBaseUrl}/cl/dashboard/agenda?date=${today}`,
    { waitUntil: 'networkidle' },
  );
  if (await ctx.session.detectExpired()) {
    return {
      appointments: [],
      fetched_at: new Date().toISOString(),
      session: { needs_reauth: true },
    };
  }
  const result = await sh.extract(
    `List ALL appointments on ${today}. For each: external_ref (the appointment id), starts_at + ends_at as ISO datetimes, service_name, barber_external_id, customer_name, customer_phone, status. Use null for missing fields.`,
    TODAY_SCHEMA,
  );
  return {
    appointments: result.appointments ?? [],
    fetched_at: new Date().toISOString(),
    session: { needs_reauth: false },
  };
}
