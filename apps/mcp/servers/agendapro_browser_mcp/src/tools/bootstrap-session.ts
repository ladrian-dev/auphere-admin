/**
 * agendapro._bootstrap_session — operator-only.
 *
 * Login inicial. Captura context_id que el adapter Python persiste en
 * tenant_credentials (Fernet). Solo invocado por el endpoint admin
 * ``POST /admin/tenants/:id/integrations/agendapro/bootstrap``.
 */

import { randomUUID } from 'node:crypto';

import type { ServerConfig } from '../config.js';
import {
  type BootstrapSessionOutput,
  BootstrapSessionInputSchema,
} from '../schemas.js';
import type { ScreenshotStore } from '../screenshot-store.js';
import { defaultLoginRunner, type LoginRunner } from '../stagehand/login.js';
import type { BrowserSession } from '../stagehand/session.js';

export async function bootstrapSession(
  rawArgs: unknown,
  ctx: {
    config: ServerConfig;
    session: BrowserSession;
    screenshotStore: ScreenshotStore;
    loginRunner?: LoginRunner;
  },
): Promise<BootstrapSessionOutput> {
  const args = BootstrapSessionInputSchema.parse(rawArgs);
  const runner = ctx.loginRunner ?? defaultLoginRunner;
  const result = await runner(ctx.config, {
    login: args.login,
    password: args.password,
    businessUrl: args.business_url ?? undefined,
  });
  // Optionally take a confirmation screenshot via a fresh session against
  // the new context_id.
  let screenshotUrl: string | null = null;
  let screenshotFailed = false;
  let screenshotError: string | null = null;
  try {
    await ctx.session.ensureAttached(result.contextId);
    const png = await ctx.session.screenshot();
    screenshotUrl = await ctx.screenshotStore.put({
      tenantId: ctx.config.tenantId,
      auditId: randomUUID(),
      png,
    });
  } catch (err) {
    screenshotFailed = true;
    screenshotError = (err as Error).message;
  }
  return {
    context_id: result.contextId,
    bootstrap_at: new Date().toISOString(),
    screenshot: {
      screenshot_url: screenshotUrl,
      screenshot_failed: screenshotFailed,
      screenshot_error: screenshotError,
    },
  };
}
