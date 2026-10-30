import "server-only";

import { BackendError } from "@/lib/backend";

export type Loaded<T> = { ok: true; data: T } | { ok: false; status: number | null };

/**
 * A read of the screen, kept apart from the others: one that fails leaves the
 * rest of the page standing, and says whether it was the panel's token (`401`)
 * or the API.
 */
export async function load<T>(read: () => Promise<T>): Promise<Loaded<T>> {
  try {
    return { ok: true, data: await read() };
  } catch (err) {
    return { ok: false, status: err instanceof BackendError ? err.status : null };
  }
}
