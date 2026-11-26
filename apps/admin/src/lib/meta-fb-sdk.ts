/**
 * Lazy loader for the Facebook JavaScript SDK + Embedded Signup helper.
 *
 * The SDK is NOT eagerly loaded — bundling it would block the rest of the
 * admin panel on a script we only need when an operator clicks "Conectar
 * WhatsApp (Meta)". The first call to ``loadFbSdk`` injects the script tag,
 * subsequent calls reuse the cached promise.
 *
 * Once the SDK loads we call ``FB.init`` with the Auphere App ID + a
 * recent Graph API version. Both come from ``NEXT_PUBLIC_*`` env vars so a
 * dev/staging app can be wired in without rebuilding (only redeploy).
 *
 * Public surface:
 *   - ``loadFbSdk()``                     ensure the SDK is ready
 *   - ``loginWithMeta(configId, exts?)``  open Embedded Signup popup
 *   - ``MetaSignupEnvelope``              shape returned on success
 */

declare global {
  interface Window {
    FB?: FbSdk;
    fbAsyncInit?: () => void;
  }
}

interface FbSdk {
  init(opts: {
    appId: string;
    version: string;
    xfbml?: boolean;
    cookie?: boolean;
  }): void;
  login(
    cb: (response: FbLoginResponse) => void,
    opts: {
      config_id: string;
      response_type: "code";
      override_default_response_type?: boolean;
      extras?: Record<string, unknown>;
      scope?: string;
    },
  ): void;
}

interface FbLoginResponse {
  authResponse?: {
    code?: string;
    accessToken?: string;
    userID?: string;
    expiresIn?: number;
  };
  status?: string;
}

/** What the Embedded Signup popup attaches to the parent window after the
 *  user finishes. Meta sends a ``message`` event with ``type`` =
 *  ``'WA_EMBEDDED_SIGNUP'`` and one of two events depending on the flow:
 *
 *   - Cloud API → ``event: 'FINISH'`` with ``data.waba_id``,
 *     ``data.phone_number_id``, ``data.business_id``.
 *   - Coexistence → ``event: 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING'``
 *     with ONLY ``data.waba_id``. The backend derives the rest from
 *     ``GET /{waba_id}/phone_numbers``.
 *
 *  The OAuth ``code`` comes *separately* via the ``FB.login`` callback. */
export interface MetaSignupEnvelope {
  code: string;
  waba_id: string;
  phone_number_id?: string;
  business_id?: string;
}

/** Env-var reads use DOT notation (``process.env.NEXT_PUBLIC_*``) so
 *  Next.js can statically inline the values into the client bundle at
 *  build time. Bracket notation (``process.env[name]``) would NOT be
 *  replaced — it returns ``undefined`` at runtime in the browser, even
 *  when the variable exists in Vercel's environment. Learned the hard
 *  way 2026-05-21. Keep this pattern.
 */
const META_APP_ID = process.env.NEXT_PUBLIC_META_APP_ID;
const META_GRAPH_VERSION =
  process.env.NEXT_PUBLIC_META_GRAPH_API_VERSION ?? "v26.0";
/** Spec 050: Embedded Signup v4 until v5 passes the five paths in staging. */
const META_SIGNUP_VERSION: SignupVersion =
  process.env.NEXT_PUBLIC_META_EMBEDDED_SIGNUP_VERSION === "v5" ? "v5" : "v4";
export const META_CONFIG_ID_CLOUD_API =
  process.env.NEXT_PUBLIC_META_CONFIG_ID_WA_CLOUD_API;
export const META_CONFIG_ID_COEXISTENCE =
  process.env.NEXT_PUBLIC_META_CONFIG_ID_WA_COEXISTENCE;

function requireAppId(): string {
  if (!META_APP_ID) {
    throw new Error(
      "Missing env var NEXT_PUBLIC_META_APP_ID. Add it to Vercel + .env.local and rebuild.",
    );
  }
  return META_APP_ID;
}

/** Exact origins Meta posts Embedded Signup messages from. */
const META_ORIGINS = new Set([
  "https://www.facebook.com",
  "https://web.facebook.com",
  "https://business.facebook.com",
]);

let sdkPromise: Promise<FbSdk> | null = null;

export function loadFbSdk(): Promise<FbSdk> {
  if (typeof window === "undefined") {
    return Promise.reject(
      new Error("loadFbSdk must run in the browser (no SSR)."),
    );
  }
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<FbSdk>((resolve, reject) => {
    const appId = requireAppId();
    if (window.FB) {
      window.FB.init({ appId, version: META_GRAPH_VERSION });
      resolve(window.FB);
      return;
    }
    window.fbAsyncInit = () => {
      try {
        window.FB!.init({ appId, version: META_GRAPH_VERSION });
        resolve(window.FB!);
      } catch (err) {
        reject(err instanceof Error ? err : new Error(String(err)));
      }
    };
    const script = document.createElement("script");
    script.async = true;
    script.defer = true;
    script.crossOrigin = "anonymous";
    script.src = "https://connect.facebook.net/en_US/sdk.js";
    script.onerror = () => {
      // Forget the failed load so the next attempt tries again (as the console does).
      sdkPromise = null;
      reject(new Error("Failed to load Facebook SDK script"));
    };
    document.body.appendChild(script);
  });
  return sdkPromise;
}

/** Embedded Signup mode. Determines which ``featureType`` we pass to
 *  ``FB.login`` — the configuration ID alone does NOT differentiate the
 *  flow; Meta dispatches based on extras.featureType. Learned the hard
 *  way 2026-05-21 when both modes were sending the user through the
 *  same wizard.
 */
export type SignupMode = "cloud_api" | "coexistence";

/** What the operator reads when the wait ends without a number (spec 049, 7.2). */
const WAIT_TEXT = {
  closed: "Se cerró la ventana de Meta antes de terminar. No se conectó nada.",
  declined: "El cliente no autorizó los permisos. No se conectó nada.",
  noCode: "Meta no devolvió el código de autorización: revisa que la configuración pida response_type=code.",
  cancelled: "Se canceló la espera de la ventana de Meta.",
  timeout: "Meta no respondió a tiempo (5 minutos). Vuelve a intentarlo.",
} as const;

const TIMEOUT_MS = 5 * 60 * 1000;

/** The attempt in flight; a new one ends it, so only one listener and one deadline live. */
let endCurrentAttempt: (() => void) | null = null;

/**
 * Open the Embedded Signup popup with the chosen configuration and
 * resolve with the data the backend needs to complete signup.
 *
 * Two channels of information arrive — the OAuth ``code`` comes through
 * the ``FB.login`` callback, and the WABA / phone / business IDs come
 * through a ``postMessage`` event from the popup. Both are needed.
 *
 * Spec 047 (30.4, T101) and 049 (7.2, 2026-11-26), same as the console:
 * the wait always ends, and every way out removes the listener and the
 * deadline.
 *
 *   - One 5 min deadline starts before the SDK loads, so an SDK that
 *     never arrives ends too.
 *   - ``signal`` cancels at once; whatever Meta sends after that is dropped.
 *   - A new call ends the previous attempt the same way.
 *   - ``FB.login`` without a code and not ``connected`` is the window
 *     being closed (or the permissions declined), and is said so.
 */
export function loginWithMeta(
  configId: string,
  mode: SignupMode = "cloud_api",
  signupVersion: SignupVersion = META_SIGNUP_VERSION,
  signal?: AbortSignal,
): Promise<MetaSignupEnvelope> {
  endCurrentAttempt?.();
  return new Promise<MetaSignupEnvelope>((resolve, reject) => {
    let code: string | undefined;
    let data: Omit<MetaSignupEnvelope, "code"> | undefined;
    let settled = false;
    const end = () => fail(new Error(WAIT_TEXT.cancelled));
    const timer = setTimeout(() => fail(new Error(WAIT_TEXT.timeout)), TIMEOUT_MS);

    function cleanup() {
      settled = true;
      clearTimeout(timer);
      window.removeEventListener("message", onMessage);
      signal?.removeEventListener("abort", end);
      if (endCurrentAttempt === end) endCurrentAttempt = null;
    }
    function fail(err: unknown) {
      if (settled) return;
      cleanup();
      reject(err instanceof Error ? err : new Error(String(err)));
    }
    function finishIfBoth() {
      if (settled || code === undefined || data === undefined) return;
      cleanup();
      resolve({ code, ...data });
    }
    function onMessage(event: MessageEvent) {
      // Origin guard: Meta's exact origins, never a suffix match
      // (``evilfacebook.com`` ends in ``facebook.com`` too).
      if (typeof event.origin !== "string" || !META_ORIGINS.has(event.origin)) {
        return;
      }
      // Meta posts the envelope as a JSON STRING, not as an object. Older
      // versions of this file checked `typeof event.data === "object"` and
      // silently dropped every event — the dialog stayed in "Conectando…"
      // forever even though the WABA was already attached server-side at
      // Meta. Always JSON.parse first; tolerate the (rare) case where Meta
      // sends an already-parsed object.
      const msg = parseMetaSignupMessage(event.data);
      if (msg === null) return;
      if (typeof console !== "undefined") {
        console.debug("[meta-fb-sdk] postMessage received", msg);
      }
      // Same decision as the console (spec 050): both v4 FINISH events and
      // v5's FINISH (WABA in ``messaging_account_ids``) are success;
      // FINISH_ONLY_WABA / FINISH_GRANT_ONLY_API_ACCESS say what is missing.
      const outcome = signupOutcome(msg);
      if (outcome === null) return;
      if (outcome.kind === "failed") {
        fail(new Error(FAILURE_TEXT[outcome.code](outcome.detail)));
        return;
      }
      data = {
        waba_id: outcome.waba_id,
        phone_number_id: outcome.phone_number_id,
        business_id: outcome.business_id,
      };
      finishIfBoth();
    }

    if (signal?.aborted) return end();
    endCurrentAttempt = end;
    signal?.addEventListener("abort", end, { once: true });
    // Listen BEFORE the popup opens: Meta sometimes posts before the
    // FB.login callback resolves.
    window.addEventListener("message", onMessage);
    // ``.catch`` after ``.then``: a ``FB.login`` that throws (popup refused)
    // ends the wait too.
    loadFbSdk()
      .then((sdk) => {
        if (settled) return;
        sdk.login(
          (response) => {
            if (!response.authResponse?.code) {
              fail(
                new Error(
                  response.status === "connected"
                    ? WAIT_TEXT.noCode
                    : response.status === "not_authorized"
                      ? WAIT_TEXT.declined
                      : WAIT_TEXT.closed,
                ),
              );
              return;
            }
            code = response.authResponse.code;
            finishIfBoth();
          },
          {
            config_id: configId,
            response_type: "code",
            override_default_response_type: true,
            // ``featureType`` (v4) is THE differentiator between Cloud API and
            // Coexistence: the configuration ID alone routes both to the same
            // wizard. v5 turns coexistence on by default. See ``signupExtras``.
            extras: signupExtras(mode, signupVersion),
          },
        );
      })
      .catch(fail);
  });
}

// ── postMessage shape ──────────────────────────────────────────────────────
//
// Spec 050: the pure part below is the same as the console's
// (``apps/console/src/lib/meta-fb-sdk.ts``); ``meta-fb-sdk-parity.test.ts``
// fails if the two drift.

export type SignupVersion = "v4" | "v5";

export interface MetaSignupMessage {
  type: "WA_EMBEDDED_SIGNUP";
  event:
    | "FINISH"
    | "FINISH_ONLY_WABA"
    | "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"
    | "FINISH_GRANT_ONLY_API_ACCESS"
    | "CANCEL"
    | "ERROR";
  data?: {
    waba_id?: string;
    phone_number_id?: string;
    business_id?: string;
    /** v5: the WABA comes here instead of ``waba_id``. */
    messaging_account_ids?: string[] | string;
    error_message?: string;
    current_step?: string;
  };
}

/** Parse a postMessage payload into a :class:`MetaSignupMessage`, or
 *  ``null`` if the message isn't a WhatsApp Embedded Signup event.
 *
 *  Meta posts the envelope as a JSON STRING. Tolerate the (rare) case
 *  where a different SDK version posts an already-parsed object. Anything
 *  else (other iframes, browser extensions, devtools messages, etc.) is
 *  silently ignored.
 */
export function parseMetaSignupMessage(raw: unknown): MetaSignupMessage | null {
  let parsed: unknown = raw;
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const candidate = parsed as { type?: unknown };
  if (candidate.type !== "WA_EMBEDDED_SIGNUP") return null;
  return parsed as MetaSignupMessage;
}

export type SignupFailureCode =
  | "cancelled"
  | "meta_error"
  | "no_number"
  | "grant_only";

export type SignupOutcome =
  | {
      kind: "finished";
      waba_id: string;
      phone_number_id?: string;
      business_id?: string;
    }
  | { kind: "failed"; code: SignupFailureCode; detail?: string };

const FAILURE_TEXT: Record<SignupFailureCode, (detail?: string) => string> = {
  cancelled: () => "El cliente canceló el flow de conexión.",
  meta_error: (detail) =>
    `Meta devolvió un error: ${detail ?? "desconocido"}`,
  no_number: () =>
    "La WABA quedó creada, pero sin número. Vuelve a abrir Meta y añade el número.",
  grant_only: () =>
    "Meta dio acceso a la cuenta, pero no compartió ningún número. Vuelve a abrir Meta y elige el número.",
};

function firstId(ids: string[] | string | undefined): string | undefined {
  const id = Array.isArray(ids) ? ids[0] : ids;
  return typeof id === "string" && id ? id : undefined;
}

/** Pure: what a parsed message means, or ``null`` while the wizard is open. */
export function signupOutcome(
  msg: MetaSignupMessage | null,
): SignupOutcome | null {
  if (msg === null) return null;
  const data = msg.data ?? {};
  switch (msg.event) {
    case "FINISH":
    case "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING": {
      const waba = data.waba_id || firstId(data.messaging_account_ids);
      if (!waba) {
        return {
          kind: "failed",
          code: "meta_error",
          detail: `${msg.event} without waba_id`,
        };
      }
      return {
        kind: "finished",
        waba_id: waba,
        phone_number_id: data.phone_number_id || undefined,
        business_id: data.business_id || undefined,
      };
    }
    case "FINISH_ONLY_WABA":
      return { kind: "failed", code: "no_number" };
    case "FINISH_GRANT_ONLY_API_ACCESS":
      return { kind: "failed", code: "grant_only" };
    case "CANCEL":
      return { kind: "failed", code: "cancelled", detail: data.current_step };
    case "ERROR":
      return { kind: "failed", code: "meta_error", detail: data.error_message };
    default:
      return null;
  }
}

/**
 * The ``extras`` of ``FB.login``. v4: coexistence is ``featureType``,
 * Cloud API sends nothing else, and no ``sessionInfoVersion`` (retired
 * with v4). v5: coexistence is on by default, so Cloud API turns it off.
 */
export function signupExtras(
  mode: SignupMode,
  version: SignupVersion = "v4",
): Record<string, unknown> {
  if (version === "v5") {
    return mode === "coexistence"
      ? { version: "v5" }
      : {
          version: "v5",
          features: [
            { name: "whatsapp_business_app_onboarding", enabled: false },
          ],
        };
  }
  return mode === "coexistence"
    ? { setup: {}, featureType: "whatsapp_business_app_onboarding" }
    : { setup: {} };
}
