import * as WebBrowser from "expo-web-browser";

import { endpoints, type Tokens } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import { API_URL, APP_VERSION, AUTH_REDIRECT, PLATFORM } from "@/config";
import type { Locale } from "@/i18n/t";

import { displayName } from "./device";
import { createPkce } from "./pkce";
import type { Session } from "./store";

/**
 * Signing in (spec 031, R1 as amended on 2026-10-20, contracts/phone-auth.md).
 * The app has its own way in; nothing goes through the partner console.
 *
 * - **Email and password**, typed here and checked by the API with the web's
 *   rules. The password is never stored: only this phone's session (R1.8).
 * - **Google**, in the system's secure window: the API runs Google's web flow
 *   and hands back a one-use code bound to our PKCE challenge, which the API
 *   swaps for this phone's credentials. The Google account has to be the one
 *   of the email Auphere gave access to (R1.3).
 */
export type SignInOutcome =
  | { kind: "ok"; session: Session }
  | { kind: "cancelled" }
  | { kind: "invalid-credentials" }
  | { kind: "rate-limited" }
  | { kind: "google-mismatch" }
  | { kind: "google-unavailable" }
  | { kind: "not-a-client" }
  | { kind: "no-access" }
  | { kind: "update-required"; minimum: string | null; reason: string | null }
  | { kind: "offline" }
  | { kind: "failed" };

type Refusal = Exclude<SignInOutcome, { kind: "ok" } | { kind: "update-required" }>;

/** What a refusal code from the API (or Google's way back) means to the person. */
export function outcomeOfError(code: string | null | undefined): Refusal {
  switch (code) {
    case "invalid_credentials":
      return { kind: "invalid-credentials" };
    case "rate_limited":
      return { kind: "rate-limited" };
    // Google does not vouch for the email: to the person it is the same as the wrong account.
    case "google_account_mismatch":
    case "email_not_verified":
      return { kind: "google-mismatch" };
    case "google_unavailable":
      return { kind: "google-unavailable" };
    case "not_a_client":
      return { kind: "not-a-client" };
    case "no_access":
      return { kind: "no-access" };
    case "cancelled":
      return { kind: "cancelled" };
    default:
      return { kind: "failed" };
  }
}

function device(installId: string, locale: Locale) {
  return { platform: PLATFORM, display_name: displayName(), install_id: installId, app_version: APP_VERSION, locale };
}

function sessionOf(tokens: Tokens): SignInOutcome {
  return {
    kind: "ok",
    session: {
      phoneId: tokens.phone_id,
      accessToken: tokens.access_token,
      accessExpiresAt: Date.now() + tokens.expires_in * 1000,
      refreshToken: tokens.refresh_token,
    },
  };
}

function outcomeOf(e: unknown): SignInOutcome {
  if (!(e instanceof ApiError)) return { kind: "failed" };
  if (e.offline) return { kind: "offline" };
  if (e.code === "app_update_required") {
    return {
      kind: "update-required",
      minimum: typeof e.info.minimum_version === "string" ? e.info.minimum_version : null,
      reason: typeof e.info.reason === "string" ? e.info.reason : null,
    };
  }
  return outcomeOfError(e.code);
}

export async function signInWithPassword(email: string, password: string, installId: string, locale: Locale): Promise<SignInOutcome> {
  try {
    return sessionOf(await endpoints.signInWithPassword({ email, password, ...device(installId, locale) }));
  } catch (e) {
    return outcomeOf(e);
  }
}

export function googleUrl(p: { challenge: string; state: string }): string {
  const q = new URLSearchParams({ state: p.state, code_challenge: p.challenge });
  return `${API_URL}/app/sign-in/google?${q.toString()}`;
}

/** What came back to `auphere-customers://auth/callback`, checked against our `state`. */
export function readCallback(url: string, state: string): { code: string } | { error: string } {
  const query = url.split("?")[1] ?? "";
  const params = new URLSearchParams(query.split("#")[0]);
  if (params.get("state") !== state) return { error: "state_mismatch" };
  const error = params.get("error");
  if (error) return { error };
  const code = params.get("code");
  return code ? { code } : { error: "no_code" };
}

export async function signInWithGoogle(installId: string, locale: Locale): Promise<SignInOutcome> {
  const pkce = await createPkce();
  let result: WebBrowser.WebBrowserAuthSessionResult;
  try {
    result = await WebBrowser.openAuthSessionAsync(googleUrl(pkce), AUTH_REDIRECT, {
      // Share the browser's cookies: already signed in to Google there → one tap.
      preferEphemeralSession: false,
      showInRecents: false,
    });
  } catch {
    return { kind: "failed" };
  }
  if (result.type !== "success") return { kind: "cancelled" };

  const back = readCallback(result.url, pkce.state);
  if ("error" in back) return outcomeOfError(back.error);

  try {
    return sessionOf(await endpoints.signInWithGoogle({ code: back.code, code_verifier: pkce.verifier, ...device(installId, locale) }));
  } catch (e) {
    return outcomeOf(e);
  }
}
