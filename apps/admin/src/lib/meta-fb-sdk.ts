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
  process.env.NEXT_PUBLIC_META_GRAPH_API_VERSION ?? "v22.0";
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
      if (!isMetaSignupMessage(event)) return;
      const data = event.data as MetaSignupMessage;
      // Cloud API completes with "FINISH" carrying all three ids.
      // Coexistence completes with "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"
      // carrying only waba_id — the backend derives phone_number_id from
      // GET /{waba_id}/phone_numbers. Treat both as success.
      const isFinish =
        data.event === "FINISH" ||
        data.event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING";
      if (isFinish && data.data) {
        window.removeEventListener("message", onMessage);
        const waba = data.data.waba_id;
        if (!waba) {
          reject(new Error("Meta devolvió FINISH sin waba_id."));
          return;
        }
        resolve({
          waba_id: waba,
          phone_number_id: data.data.phone_number_id || undefined,
          business_id: data.data.business_id || undefined,
        });
      } else if (data.event === "CANCEL" || data.event === "ERROR") {
        window.removeEventListener("message", onMessage);
        reject(
          new Error(
            data.event === "CANCEL"
              ? "El cliente canceló el flow de conexión."
              : `Meta devolvió un error: ${data.data?.error_message ?? "desconocido"}`,
          ),
        );
      }
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
        // ``featureType`` is THE differentiator between Cloud API and
        // Coexistence flows. The configuration ID alone routes the user to
        // the same WhatsApp Cloud onboarding wizard; only this extras field
        // makes Meta render the Coexistence path that preserves the
        // tenant's WhatsApp Business mobile app.
        //
        //   Cloud API    → featureType: "" (or omitted)
        //   Coexistence  → featureType: "whatsapp_business_app_onboarding"
        //
        // ``sessionInfoVersion: "3"`` matches the postMessage envelope
        // schema we already parse (data.event, data.data.waba_id, etc.).
        extras: {
          setup: {},
          featureType:
            mode === "coexistence"
              ? "whatsapp_business_app_onboarding"
              : "",
          sessionInfoVersion: "3",
        },
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

interface MetaSignupMessage {
  type: "WA_EMBEDDED_SIGNUP";
  // Cloud API → "FINISH". Coexistence → "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING".
  event:
    | "FINISH"
    | "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"
    | "CANCEL"
    | "ERROR";
  data?: {
    waba_id?: string;
    phone_number_id?: string;
    business_id?: string;
    error_message?: string;
  };
}

function isMetaSignupMessage(event: MessageEvent): boolean {
  if (typeof event.data !== "object" || event.data === null) return false;
  const data = event.data as { type?: unknown };
  return data.type === "WA_EMBEDDED_SIGNUP";
}
