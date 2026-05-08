/**
 * Login flow contra AgendaPro.
 *
 * Bloque E ships una implementación pragmática basada en Stagehand
 * ``act()`` (LLM-driven selectors) — sobrevive cambios de DOM moderados.
 * Para AgendaPro CL la URL típica es:
 *   https://www.agendapro.com/cl/users/sign_in
 *
 * El bootstrap completo:
 *   1. Browserbase: crear context nuevo (sin contextId).
 *   2. Stagehand attach a sesión + ese context.
 *   3. Navegar al login URL.
 *   4. Llenar email + password (Stagehand act).
 *   5. Click submit.
 *   6. Verificar URL final ≠ login (success) o lanzar error.
 *   7. Devolver context_id (que ahora persiste el cookie de sesión).
 */

import { Browserbase } from '@browserbasehq/sdk';
import { Stagehand } from '@browserbasehq/stagehand';

import type { ServerConfig } from '../config.js';
import { log } from '../logging.js';

export interface LoginResult {
  contextId: string;
  finalUrl: string;
}

export interface LoginInput {
  login: string;
  password: string;
  businessUrl?: string;
  /** Si se pasa, reusa este context (caso re-login auto). */
  existingContextId?: string;
}

/** Login que devuelve un nuevo context_id. Implementación inyectable
 * para tests (no spawnea Browserbase). */
export type LoginRunner = (
  config: ServerConfig,
  input: LoginInput,
) => Promise<LoginResult>;

export const defaultLoginRunner: LoginRunner = async (config, input) => {
  const bb = new Browserbase({ apiKey: config.browserbaseApiKey });

  // 1. Create or reuse context.
  let contextId = input.existingContextId;
  if (!contextId) {
    const ctx = await bb.contexts.create({ projectId: config.browserbaseProjectId });
    contextId = ctx.id;
    log.info({ contextId }, 'browserbase.context_created');
  }

  // 2. Open a session attached to that context with persist=true so the
  //    login cookies survive the session ending.
  const session = await bb.sessions.create({
    projectId: config.browserbaseProjectId,
    browserSettings: {
      context: { id: contextId, persist: true },
    },
  });

  const sh = new Stagehand({
    env: 'BROWSERBASE',
    apiKey: config.browserbaseApiKey,
    projectId: config.browserbaseProjectId,
    browserbaseSessionID: session.id,
    verbose: 0,
    logger: (msg: { category?: string; message?: string }) => {
      log.debug({ category: msg.category, message: msg.message }, 'stagehand.login');
    },
  });

  try {
    await sh.init();
    const loginUrl =
      input.businessUrl ?? `${config.agendaproBaseUrl}/cl/users/sign_in`;
    await sh.page.goto(loginUrl, { waitUntil: 'networkidle' });

    // Stagehand act-based form fill — robust to label drift.
    await sh.page.act(
      `Type the email "${input.login}" into the email or username field`,
    );
    await sh.page.act(
      `Type the password "${input.password}" into the password field`,
    );
    await sh.page.act('Click the sign in / login button');

    // Wait for redirect away from login.
    await sh.page.waitForLoadState('networkidle', { timeout: 30_000 });
    const finalUrl = sh.page.url();
    if (/\/(login|sign_in|sessions\/new)\b/i.test(finalUrl)) {
      throw new Error(`login failed — still on login page: ${finalUrl}`);
    }
    log.info({ finalUrl, contextId }, 'login.success');
    return { contextId, finalUrl };
  } finally {
    await sh.close().catch((err) => {
      log.warn({ err: (err as Error).message }, 'login.close_failed');
    });
  }
};
