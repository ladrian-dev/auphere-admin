/**
 * Sesión Stagehand + Browserbase Context para un tenant.
 *
 * El proceso es per-tenant — solo una sesión activa a la vez. El
 * adapter Python pasa ``context_id`` en cada call; si difiere del
 * cached, se re-attach.
 *
 * Diseño:
 * - Lazy init: la primera tool call que necesita browser dispara
 *   ``ensureAttached(context_id)``.
 * - Re-use entre calls: el browser handle vive entre tool calls del
 *   mismo proceso.
 * - Cleanup en SIGTERM / proceso exit.
 *
 * Stagehand fallback LLM-based selector: cuando AgendaPro cambia su DOM
 * mid-sprint, ``page.act()`` permite describir la acción en lenguaje
 * natural y Stagehand resuelve el selector. Las tools usan ``act()``
 * para acciones complejas y ``locator()`` para selectores estables.
 */

import { Browserbase } from '@browserbasehq/sdk';
import { Stagehand } from '@browserbasehq/stagehand';

import type { ServerConfig } from '../config.js';
import { log } from '../logging.js';
import { pageOf } from './page.js';

export interface BrowserSession {
  /** Asegura que la sesión está attach'd al contextId dado. Re-attach si difiere. */
  ensureAttached(contextId: string): Promise<void>;
  /** Stagehand instance ready to drive. Throws if not attached yet. */
  stagehand(): Stagehand;
  /** Take a screenshot of the current page. Returns PNG buffer. */
  screenshot(): Promise<Buffer>;
  /** Has the current page been redirected to AgendaPro's login page? */
  detectExpired(): Promise<boolean>;
  /** Close + cleanup. */
  close(): Promise<void>;
}

/** Fake-friendly factory: tests inject a mock session by overriding this. */
export type SessionFactory = (config: ServerConfig) => BrowserSession;

export const defaultSessionFactory: SessionFactory = (config) =>
  new BrowserbaseStagehandSession(config);

class BrowserbaseStagehandSession implements BrowserSession {
  private currentContextId: string | null = null;
  private sh: Stagehand | null = null;
  private bb: Browserbase | null = null;

  constructor(private readonly config: ServerConfig) {}

  async ensureAttached(contextId: string): Promise<void> {
    if (this.sh && this.currentContextId === contextId) return;
    if (this.sh) {
      log.info({ from: this.currentContextId, to: contextId }, 'session.reattach');
      try {
        await this.sh.close();
      } catch (err) {
        log.warn({ err: (err as Error).message }, 'session.close_before_reattach_failed');
      }
      this.sh = null;
    }
    if (!this.bb) {
      this.bb = new Browserbase({ apiKey: this.config.browserbaseApiKey });
    }
    // Reuse existing context — cookies + storage persisten cross-session.
    const session = await this.bb.sessions.create({
      projectId: this.config.browserbaseProjectId,
      browserSettings: {
        context: { id: contextId, persist: true },
      },
    });
    log.info(
      { sessionId: session.id, contextId },
      'browserbase.session_created',
    );
    this.sh = new Stagehand({
      env: 'BROWSERBASE',
      apiKey: this.config.browserbaseApiKey,
      projectId: this.config.browserbaseProjectId,
      browserbaseSessionID: session.id,
      verbose: 0,
      // Logger to stderr only — gotcha #4.
      logger: (msg: { category?: string; message?: string }) => {
        log.debug({ category: msg.category, message: msg.message }, 'stagehand');
      },
    });
    await this.sh.init();
    this.currentContextId = contextId;
  }

  stagehand(): Stagehand {
    if (!this.sh) throw new Error('session not attached — call ensureAttached() first');
    return this.sh;
  }

  async screenshot(): Promise<Buffer> {
    const sh = this.stagehand();
    const page = await pageOf(sh);
    const buf = await page.screenshot({ fullPage: false });
    return Buffer.from(buf);
  }

  async detectExpired(): Promise<boolean> {
    if (!this.sh) return false;
    try {
      const page = await pageOf(this.sh);
      const url = page.url();
      // AgendaPro login URLs típicas: /login, /sign_in, /sessions/new.
      if (/\/(login|sign_in|sessions\/new)\b/i.test(url)) return true;
      // Fallback: look for a password input on the current page.
      const hasPassword = await page
        .locator('input[type="password"]')
        .count();
      return hasPassword > 0;
    } catch (err) {
      log.warn({ err: (err as Error).message }, 'session.detectExpired_failed');
      return false;
    }
  }

  async close(): Promise<void> {
    if (this.sh) {
      try {
        await this.sh.close();
      } catch (err) {
        log.warn({ err: (err as Error).message }, 'session.close_failed');
      }
    }
    this.sh = null;
    this.currentContextId = null;
  }
}
