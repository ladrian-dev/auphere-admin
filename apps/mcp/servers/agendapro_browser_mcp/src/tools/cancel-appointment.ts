/**
 * agendapro.cancel_appointment — mutativa.
 *
 * Idempotente: si la cita ya está cancelada, no-op (devuelve OK con
 * screenshot del estado actual).
 */

import type { ServerConfig } from '../config.js';
import { log } from '../logging.js';
import {
  type CancelAppointmentOutput,
  CancelAppointmentInputSchema,
} from '../schemas.js';
import type { ScreenshotStore } from '../screenshot-store.js';
import type { BrowserSession } from '../stagehand/session.js';
import { _internalCaptureScreenshot } from './create-appointment.js';

export async function cancelAppointment(
  rawArgs: unknown,
  ctx: {
    session: BrowserSession;
    screenshotStore: ScreenshotStore;
    config: ServerConfig;
  },
): Promise<CancelAppointmentOutput> {
  const args = CancelAppointmentInputSchema.parse(rawArgs);
  if (!args.context_id) {
    throw new Error('context_id is required for cancel_appointment');
  }
  await ctx.session.ensureAttached(args.context_id);
  const sh = ctx.session.stagehand();

  await sh.page.goto(
    `${ctx.config.agendaproBaseUrl}/cl/dashboard/agenda/appointments/${args.external_ref}`,
    { waitUntil: 'networkidle' },
  );
  if (await ctx.session.detectExpired()) {
    return {
      external_ref: args.external_ref,
      status: 'cancelled',
      screenshot: { screenshot_url: null, screenshot_failed: true, screenshot_error: 'session_expired' },
      session: { needs_reauth: true },
    };
  }

  await sh.page.act('Click the Cancel appointment button');
  if (args.reason) {
    await sh.page.act(`Type the cancellation reason "${args.reason}"`);
  }
  await sh.page.act('Confirm the cancellation in the dialog');
  await sh.page.waitForLoadState('networkidle', { timeout: 30_000 });

  const screenshot = await _internalCaptureScreenshot(ctx, args.context_id);
  log.info({ external_ref: args.external_ref }, 'cancel.done');
  return {
    external_ref: args.external_ref,
    status: 'cancelled',
    screenshot,
    session: { needs_reauth: false },
  };
}
