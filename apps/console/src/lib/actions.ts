import "server-only";

import { BackendError } from "./backend";

/** Uniform result for Server Actions: never throw a backend error to the client. */
export type ActionResult<T = null> =
  | { ok: true; data: T }
  | {
      ok: false;
      status: number;
      message: string;
      /** Closed-vocabulary code when the endpoint sent a structured detail.
       *  The screen writes the sentence from this; ``message`` is for logs,
       *  never for a person (principle III). */
      code?: string | null;
      info?: Record<string, unknown>;
    };

export async function run<T>(fn: () => Promise<T>): Promise<ActionResult<T>> {
  try {
    return { ok: true, data: await fn() };
  } catch (err) {
    if (err instanceof BackendError) {
      return { ok: false, status: err.status, message: err.detail, code: err.code, info: err.info };
    }
    throw err;
  }
}
