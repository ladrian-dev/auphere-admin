/**
 * agendapro.modify_appointment — mutativa.
 */

import type { ServerConfig } from '../config.js';
import { log } from '../logging.js';
import {
  type ModifyAppointmentOutput,
  ModifyAppointmentInputSchema,
} from '../schemas.js';
import type { ScreenshotStore } from '../screenshot-store.js';
import { pageOf } from '../stagehand/page.js';
import type { BrowserSession } from '../stagehand/session.js';
import { _internalCaptureScreenshot } from './create-appointment.js';

export async function modifyAppointment(
  rawArgs: unknown,
  ctx: {
    session: BrowserSession;
    screenshotStore: ScreenshotStore;
    config: ServerConfig;
  },
): Promise<ModifyAppointmentOutput> {
  const args = ModifyAppointmentInputSchema.parse(rawArgs);
  if (!args.context_id) {
    throw new Error('context_id is required for modify_appointment');
  }
  await ctx.session.ensureAttached(args.context_id);
  const sh = ctx.session.stagehand();
  const page = await pageOf(sh);

  await page.goto(
    `${ctx.config.agendaproBaseUrl}/cl/dashboard/agenda/appointments/${args.external_ref}/edit`,
    { waitUntil: 'networkidle' },
  );
  if (await ctx.session.detectExpired()) {
    return {
      appointment: {
        external_ref: args.external_ref,
        starts_at: args.new_starts_at ?? '',
        ends_at: '',
        service_name: args.new_service_name ?? '',
        barber_external_id: args.new_barber_external_id ?? null,
        customer_name: null,
        customer_phone: null,
        status: 'booked',
        management_url: null,
      },
      status: 'no_changes',
      screenshot: { screenshot_url: null, screenshot_failed: true, screenshot_error: 'session_expired' },
      session: { needs_reauth: true },
    };
  }

  let touched = false;
  if (args.new_starts_at) {
    const time = args.new_starts_at.slice(11, 16);
    await sh.act(`Change the appointment time to ${time}`);
    touched = true;
  }
  if (args.new_duration_min) {
    await sh.act(`Change the duration to ${args.new_duration_min} minutes`);
    touched = true;
  }
  if (args.new_barber_external_id) {
    await sh.act(
      `Change the assigned professional to id ${args.new_barber_external_id}`,
    );
    touched = true;
  }
  if (args.new_service_name) {
    await sh.act(`Change the service to "${args.new_service_name}"`);
    touched = true;
  }
  if (touched) {
    await sh.act('Click the Save / Update button');
    await page.waitForLoadState('networkidle', 30_000);
  }

  const screenshot = await _internalCaptureScreenshot(ctx, args.context_id);
  log.info({ external_ref: args.external_ref, touched }, 'modify.done');
  return {
    appointment: {
      external_ref: args.external_ref,
      starts_at: args.new_starts_at ?? '',
      ends_at: '',
      service_name: args.new_service_name ?? '',
      barber_external_id: args.new_barber_external_id ?? null,
      customer_name: null,
      customer_phone: null,
      status: 'booked',
      management_url: null,
    },
    status: touched ? 'modified' : 'no_changes',
    screenshot,
    session: { needs_reauth: false },
  };
}
