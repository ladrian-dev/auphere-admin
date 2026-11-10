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
    script.onerror = () =>
      reject(new Error("Failed to load Facebook SDK script"));
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

/**
 * Open the Embedded Signup popup with the chosen configuration and
 * resolve with the data the backend needs to complete signup.
 *
 * Two channels of information arrive — the OAuth ``code`` comes through
 * the ``FB.login`` callback, and the WABA / phone / business IDs come
 * through a ``postMessage`` event from the popup. We race-wait for both
 * and reject after a generous 5 min timeout (the user can take their
 * time in the popup; if they bail entirely we time out cleanly).
 */
export async function loginWithMeta(
  configId: string,
  mode: SignupMode = "cloud_api",
  signupVersion: SignupVersion = META_SIGNUP_VERSION,
): Promise<MetaSignupEnvelope> {
  const sdk = await loadFbSdk();

  // Set up the postMessage listener BEFORE opening the popup so we can't
  // miss the event (Meta sometimes fires it before the FB.login callback
  // resolves).
  const dataPromise = new Promise<{
    waba_id: string;
    phone_number_id?: string;
    business_id?: string;
  }>((resolve, reject) => {
    const onMessage = (event: MessageEvent) => {
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
      window.removeEventListener("message", onMessage);
      if (outcome.kind === "failed") {
        reject(new Error(FAILURE_TEXT[outcome.code](outcome.detail)));
        return;
      }
      resolve({
        waba_id: outcome.waba_id,
        phone_number_id: outcome.phone_number_id,
        business_id: outcome.business_id,
      });
    };
    window.addEventListener("message", onMessage);
    // Timeout safety: 5 min — popup remains open while the user logs in,
    // chooses business assets, etc. Anything longer is almost certainly
    // abandonment.
    setTimeout(
      () => {
        window.removeEventListener("message", onMessage);
        reject(new Error("Timeout esperando que el cliente termine el flow."));
      },
      5 * 60 * 1000,
    );
  });

  const codePromise = new Promise<string>((resolve, reject) => {
    sdk.login(
      (response) => {
        if (response.authResponse?.code) {
          resolve(response.authResponse.code);
        } else {
          reject(
            new Error(
              response.status === "not_authorized"
                ? "El cliente no autorizó los permisos."
                : "FB.login no devolvió code OAuth (¿popup cerrado a mitad?).",
            ),
          );
        }
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
  });

  const [code, envelopeData] = await Promise.all([codePromise, dataPromise]);
  return {
    code,
    waba_id: envelopeData.waba_id,
    phone_number_id: envelopeData.phone_number_id,
    business_id: envelopeData.business_id,
  };
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
