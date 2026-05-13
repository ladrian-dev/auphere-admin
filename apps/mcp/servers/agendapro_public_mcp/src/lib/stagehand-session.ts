/**
 * Fresh Browserbase Stealth session per call.
 *
 * Per ADR-017: no Context reuse, no cookies persisted. The trade-off
 * (slower start-up: ~3-4s for the session boot) is acceptable because
 * the customer is already waiting on the agent's ACK and the worker
 * pipeline is async.
 */

import { Stagehand } from "@browserbasehq/stagehand";

import { logger } from "./logging.js";

export interface SessionHandle {
  stagehand: Stagehand;
  /** Close the underlying browser + Browserbase session. */
  close(): Promise<void>;
}

export async function openSession(): Promise<SessionHandle> {
  const apiKey = process.env.BROWSERBASE_API_KEY;
  const projectId = process.env.BROWSERBASE_PROJECT_ID;
  if (!apiKey || !projectId) {
    throw new Error(
      "BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID must be set",
    );
  }

  const stagehand = new Stagehand({
    env: "BROWSERBASE",
    apiKey,
    projectId,
    // Anti-bot defaults per ADR-017: Stealth Mode + residential proxies
    // + reasonable defaults for selector observation. No fingerprint
    // pinning yet — Browserbase's defaults rotate fingerprints per
    // session which is what we want.
    modelName: "gemini/gemini-2.0-flash",
    enableCaching: false,
    verbose: 1,
  });

  await stagehand.init();
  logger.info(
    {
      session_id: stagehand.browserbaseSessionID ?? "unknown",
    },
    "stagehand.session.opened",
  );

  return {
    stagehand,
    async close(): Promise<void> {
      try {
        await stagehand.close();
      } catch (e) {
        logger.warn({ err: e }, "stagehand.session.close_failed");
      }
    },
  };
}
