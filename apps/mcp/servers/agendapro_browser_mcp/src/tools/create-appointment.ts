/**
 * agendapro.create_appointment — mutativa.
 *
 * Server compone idempotency key dentro del proceso (no acepta del LLM
 * ni del adapter). Captura screenshot de la confirmación y lo retorna
 * en el output (el adapter Python escribe el row de audit_log).
 */

import { randomUUID } from 'node:crypto';
import { z } from 'zod';

import type { ServerConfig } from '../config.js';
import { composeIdempotencyKey } from '../idempotency.js';
import { log } from '../logging.js';
import {
  type CreateAppointmentOutput,
  CreateAppointmentInputSchema,
  type ScreenshotMeta,
} from '../schemas.js';
import type { ScreenshotStore } from '../screenshot-store.js';
import type { BrowserSession } from '../stagehand/session.js';

const CREATE_RESULT_SCHEMA = z.object({
  external_ref: z.string(),
  status: z.enum(['booked', 'confirmed']),
  management_url: z.string().nullable().default(null),
});

export async function createAppointment(
  rawArgs: unknown,
  ctx: {
    session: BrowserSession;
    screenshotStore: ScreenshotStore;
    config: ServerConfig;
  },
): Promise<CreateAppointmentOutput> {
  const args = CreateAppointmentInputSchema.parse(rawArgs);
  if (!args.context_id) {
    throw new Error('context_id is required for create_appointment');
  }
  const idempotencyKey = composeIdempotencyKey({
    tenantId: ctx.config.tenantId,
    intentHash: args.intent_hash,
  });

  await ctx.session.ensureAttached(args.context_id);
  const sh = ctx.session.stagehand();

  // Navigate to "new appointment" form for the date+barber combo.
  const dateOnly = args.starts_at.slice(0, 10);
  const newApptUrl = `${ctx.config.agendaproBaseUrl}/cl/dashboard/agenda?date=${dateOnly}&new=1`;
  await sh.page.goto(newApptUrl, { waitUntil: 'networkidle' });

  if (await ctx.session.detectExpired()) {
    // Defensive: returning a "needs_reauth" output instead of completing
    // a half-baked appointment.
    return {
      appointment: {
        external_ref: '',
        starts_at: args.starts_at,
        ends_at: args.starts_at,
        service_name: args.service_name,
        barber_external_id: args.barber_external_id ?? null,
        customer_name: args.customer_name,
        customer_phone: args.customer_phone,
        status: 'booked',
        management_url: null,
      },
      idempotent_replay: false,
      screenshot: { screenshot_url: null, screenshot_failed: true, screenshot_error: 'session_expired' },
      session: { needs_reauth: true },
    };
  }

  // Stagehand-driven form fill. Phase 1 is best-effort: AgendaPro UI
  // varies by tenant config. The instructions are deliberately verbose
  // so the LLM-fallback recovers most label drift.
  const startTime = args.starts_at.slice(11, 16); // HH:MM
  await sh.page.act(`Select the service "${args.service_name}" in the service field`);
  if (args.barber_external_id) {
    await sh.page.act(
      `Select the professional with id ${args.barber_external_id} in the professional field`,
    );
  }
  await sh.page.act(`Set the appointment time to ${startTime}`);
  await sh.page.act(`Type the customer name "${args.customer_name}" into the client name field`);
  await sh.page.act(`Type the phone "${args.customer_phone}" into the phone field`);
  if (args.customer_email) {
    await sh.page.act(`Type the email "${args.customer_email}" into the email field`);
  }
  if (args.notes) {
    await sh.page.act(`Type "${args.notes}" into the notes/observations field`);
  }
  // Some AgendaPro forms expose an idempotency / external reference field
  // as part of the booking metadata. If not, the key is still useful for
  // our local appointments.idempotency_key — booking-server enforces it.
  log.debug({ idempotencyKey }, 'create.idempotency_composed');

  await sh.page.act('Click the "Save" or "Confirm" button to create the appointment');
  await sh.page.waitForLoadState('networkidle', { timeout: 30_000 });

  const result = await sh.page.extract({
    instruction:
      'Extract the newly-created appointment id (external_ref), status, and customer-facing management URL if visible.',
    schema: CREATE_RESULT_SCHEMA,
  });

  const screenshot = await captureScreenshot(ctx, args.context_id);
  const endsAtMs =
    new Date(args.starts_at).getTime() + args.duration_min * 60_000;
  return {
    appointment: {
      external_ref: result.external_ref,
      starts_at: args.starts_at,
      ends_at: new Date(endsAtMs).toISOString(),
      service_name: args.service_name,
      barber_external_id: args.barber_external_id ?? null,
      customer_name: args.customer_name,
      customer_phone: args.customer_phone,
      status: result.status,
      management_url: result.management_url,
    },
    idempotent_replay: false,
    screenshot,
    session: { needs_reauth: false },
  };
}

async function captureScreenshot(
  ctx: { session: BrowserSession; screenshotStore: ScreenshotStore; config: ServerConfig },
  _contextId: string,
): Promise<ScreenshotMeta> {
  try {
    const png = await ctx.session.screenshot();
    const auditId = randomUUID();
    const url = await ctx.screenshotStore.put({
      tenantId: ctx.config.tenantId,
      auditId,
      png,
    });
    return { screenshot_url: url, screenshot_failed: false, screenshot_error: null };
  } catch (err) {
    const message = (err as Error).message;
    log.warn({ err: message }, 'screenshot.capture_failed');
    return { screenshot_url: null, screenshot_failed: true, screenshot_error: message };
  }
}

export const _internalCaptureScreenshot = captureScreenshot;
