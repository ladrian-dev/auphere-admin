/**
 * agendapro._health_check — operator-only.
 *
 * Verifica que el context_id sigue logueado a AgendaPro. Si no:
 *   - Si vienen login + password: intenta re-login automático contra el
 *     mismo context (las cookies se reescriben).
 *   - Si re-login OK: devuelve healthy=true, relogin_succeeded=true,
 *     new_context_id.
 *   - Si re-login falla o no hay creds: needs_reauth=true. Adapter
 *     Python flippea ``tenant_credentials.needs_reauth``, persiste
 *     ``last_health_check_at``, y dispara escalate.escalate_to_human.
 */

import type { ServerConfig } from '../config.js';
import { log } from '../logging.js';
import {
  type HealthCheckOutput,
  HealthCheckInputSchema,
} from '../schemas.js';
import { defaultLoginRunner, type LoginRunner } from '../stagehand/login.js';
import { pageOf } from '../stagehand/page.js';
import type { BrowserSession } from '../stagehand/session.js';

export async function healthCheck(
  rawArgs: unknown,
  ctx: {
    config: ServerConfig;
    session: BrowserSession;
    loginRunner?: LoginRunner;
  },
): Promise<HealthCheckOutput> {
  const args = HealthCheckInputSchema.parse(rawArgs);
  const checkedAt = new Date().toISOString();

  let healthy = false;
  let notes: string | null = null;
  try {
    await ctx.session.ensureAttached(args.context_id);
    const sh = ctx.session.stagehand();
    const page = await pageOf(sh);
    await page.goto(
      `${ctx.config.agendaproBaseUrl}/cl/dashboard`,
      { waitUntil: 'networkidle', timeoutMs: 30_000 },
    );
    healthy = !(await ctx.session.detectExpired());
  } catch (err) {
    notes = (err as Error).message;
    log.warn({ err: notes }, 'health_check.attach_failed');
  }

  if (healthy) {
    return {
      healthy: true,
      relogin_attempted: false,
      relogin_succeeded: false,
      needs_reauth: false,
      checked_at: checkedAt,
      notes,
      new_context_id: null,
    };
  }

  // Try re-login if credentials provided.
  if (!args.login_for_relogin || !args.password_for_relogin) {
    return {
      healthy: false,
      relogin_attempted: false,
      relogin_succeeded: false,
      needs_reauth: true,
      checked_at: checkedAt,
      notes: notes ?? 'session expired and no credentials supplied for re-login',
      new_context_id: null,
    };
  }

  const runner = ctx.loginRunner ?? defaultLoginRunner;
  try {
    const reloginResult = await runner(ctx.config, {
      login: args.login_for_relogin,
      password: args.password_for_relogin,
      businessUrl: args.business_url ?? undefined,
      // Reuse the same context so cookies refresh in-place — adapter
      // doesn't have to migrate any state on tenant_credentials.
      existingContextId: args.context_id,
    });
    return {
      healthy: true,
      relogin_attempted: true,
      relogin_succeeded: true,
      needs_reauth: false,
      checked_at: checkedAt,
      notes: 'session expired; auto re-login succeeded',
      new_context_id: reloginResult.contextId,
    };
  } catch (err) {
    return {
      healthy: false,
      relogin_attempted: true,
      relogin_succeeded: false,
      needs_reauth: true,
      checked_at: checkedAt,
      notes: `auto re-login failed: ${(err as Error).message}`,
      new_context_id: null,
    };
  }
}
