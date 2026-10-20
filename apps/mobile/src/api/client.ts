import { fetch as expoFetch } from "expo/fetch";
import createClient from "openapi-fetch";

import { emitSessionEvent } from "@/auth/events";
import { clearSession, readSession, writeSession, type Session } from "@/auth/store";
import { API_URL, APP_VERSION, PLATFORM } from "@/config";

import { ApiError, errorOf } from "./errors";
import type { paths } from "./schema.gen";

/**
 * The phone's way to the API (spec 031, contracts/phone-auth.md, T026).
 *
 * - Every request says which app it is (`X-App-Platform`, `X-App-Version`):
 *   the API refuses a version under the minimum with `app_update_required`.
 * - The access token lives an hour. It is renewed **once at a time**: five
 *   requests that find it expired wait on the same renewal and are replayed.
 * - `phone_closed` from anywhere ends the session here and tells the screen
 *   why (R7.2); `app_update_required` sends the person to update (R13.1).
 */
export const APP_HEADERS = { "X-App-Platform": PLATFORM, "X-App-Version": APP_VERSION } as const;

/** Renew a little before the hour is up, so a request never leaves with a dying token. */
const EARLY_MS = 60_000;

let current: Session | null = null;
let refreshing: Promise<Session | null> | null = null;

export async function loadSession(): Promise<Session | null> {
  current = await readSession();
  return current;
}

export async function startSession(session: Session): Promise<void> {
  current = session;
  await writeSession(session);
}

/** Forget the session on this phone (the API side is `DELETE /phones/current`). */
export async function endSession(): Promise<void> {
  current = null;
  await clearSession();
}

export function hasSession(): boolean {
  return current !== null;
}

async function bodyOf(res: Pick<Response, "text">): Promise<unknown> {
  const text = await res.text().catch(() => "");
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

/** A refusal that means «this phone is no longer signed in» or «update first». */
async function handleRefusal(err: ApiError): Promise<void> {
  if (err.code === "app_update_required") {
    const minimum = typeof err.info.minimum_version === "string" ? err.info.minimum_version : null;
    const reason = typeof err.info.reason === "string" ? err.info.reason : null;
    emitSessionEvent({ type: "update-required", minimum, reason });
  } else if (err.code === "phone_closed") {
    await endSession();
    emitSessionEvent({ type: "closed", reason: typeof err.info.reason === "string" ? err.info.reason : null });
  }
}

/** A 401/403 on a route outside the typed client (the live line): the same ending as anywhere else. */
export async function settleRefusal(res: Pick<Response, "status" | "text">): Promise<void> {
  await handleRefusal(errorOf(res.status, await bodyOf(res)));
}

/** One renewal at a time; everyone who needs it waits on the same promise. */
export function refresh(): Promise<Session | null> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const before = current;
    if (!before) return null;
    let res: Response;
    try {
      res = await fetch(`${API_URL}/app/phones/refresh`, {
        method: "POST",
        headers: { ...APP_HEADERS, "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: before.refreshToken, app_version: APP_VERSION }),
      });
    } catch {
      throw new ApiError(0, "offline");
    }
    const body = await bodyOf(res);
    if (res.ok) {
      const b = body as { access_token: string; expires_in: number; refresh_token: string };
      const next: Session = {
        ...before,
        accessToken: b.access_token,
        accessExpiresAt: Date.now() + b.expires_in * 1000,
        refreshToken: b.refresh_token,
      };
      await startSession(next);
      return next;
    }
    const err = errorOf(res.status, body);
    if (res.status === 401 || res.status === 403) {
      // A renewal the API refuses never comes back: the phone is closed.
      await handleRefusal(err.code ? err : new ApiError(res.status, "phone_closed", err.info));
      return null;
    }
    throw err;
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

/** A valid access token, renewed first when it is about to expire. */
export async function accessToken(): Promise<string | null> {
  if (!current) return null;
  if (current.accessExpiresAt - Date.now() < EARLY_MS) return (await refresh())?.accessToken ?? null;
  return current.accessToken;
}

function headersWith(base: HeadersInit | undefined, token: string): Headers {
  const h = new Headers(base);
  for (const [k, v] of Object.entries(APP_HEADERS)) h.set(k, v);
  h.set("Authorization", `Bearer ${token}`);
  return h;
}

/**
 * `fetch` with the phone's credential. Bodies here are JSON (openapi-fetch);
 * uploads go through `upload()` below. A 401 renews once and replays once.
 */
export async function authedFetch(input: Request | string, init?: RequestInit): Promise<Response> {
  const req = typeof input === "string" ? new Request(input, init) : input;
  const method = req.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await req.text();
  const send = (token: string) => fetch(req.url, { method, headers: headersWith(req.headers, token), body });

  const token = await accessToken();
  if (!token) return new Response(JSON.stringify({ detail: { code: "phone_closed", reason: null } }), { status: 401 });
  let res: Response;
  try {
    res = await send(token);
    if (res.status === 401) {
      // Someone may have renewed while this request was out. Each renewal
      // invalidates the previous access token, so renewing again would cut
      // the others' — retry with the current one instead.
      const fresher = current && current.accessToken !== token ? current.accessToken : null;
      const next = fresher ?? (await refresh())?.accessToken ?? null;
      if (!next) return res;
      res = await send(next);
    }
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, "offline");
  }
  if (res.status === 401 || res.status === 403) {
    const parsed = await bodyOf(res);
    await handleRefusal(errorOf(res.status, parsed));
    return new Response(JSON.stringify(parsed), { status: res.status, headers: { "Content-Type": "application/json" } });
  }
  return res;
}

/** The typed client for `/console/lite/*`, with the phone's credential. */
export const api = createClient<paths>({ baseUrl: API_URL, fetch: authedFetch });

/** The public routes (`/app/*`): no credential, still the app's headers. */
export const publicApi = createClient<paths>({ baseUrl: API_URL, headers: APP_HEADERS });

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Unwrap an openapi-fetch result: the data, or an `ApiError` with the API's code. */
export async function call<T>(promise: Promise<Result<T>>): Promise<T> {
  let r: Result<T>;
  try {
    r = await promise;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, "offline");
  }
  if (r.response.ok) return r.data as T;
  const err = errorOf(r.response.status, r.error);
  if (r.response.status === 403 && err.code === "app_update_required") await handleRefusal(err);
  throw err;
}

/**
 * A multipart upload (an attachment), with the same credential and the same
 * one renewal on 401. `form` is built fresh for each try: a body is read once.
 */
export async function upload(path: string, form: () => FormData, headers: Record<string, string> = {}): Promise<Response> {
  // expo/fetch: it streams an expo-file-system `File` inside FormData.
  const send = (token: string) =>
    expoFetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { ...APP_HEADERS, ...headers, Authorization: `Bearer ${token}` },
      body: form(),
    }) as unknown as Promise<Response>;
  const token = await accessToken();
  if (!token) throw new ApiError(401, "phone_closed");
  try {
    let res = await send(token);
    if (res.status === 401) {
      const fresher = current && current.accessToken !== token ? current.accessToken : null;
      const next = fresher ?? (await refresh())?.accessToken ?? null;
      if (!next) return res;
      res = await send(next);
    }
    return res;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, "offline");
  }
}
