import "server-only";

import { BackendError } from "./backend";

/** Uniform result for Server Actions: never throw a backend error to the client. */
export type ActionResult<T = null> = { ok: true; data: T } | { ok: false; status: number; message: string };

export async function run<T>(fn: () => Promise<T>): Promise<ActionResult<T>> {
  try {
    return { ok: true, data: await fn() };
  } catch (err) {
    if (err instanceof BackendError) return { ok: false, status: err.status, message: err.detail };
    throw err;
  }
}
