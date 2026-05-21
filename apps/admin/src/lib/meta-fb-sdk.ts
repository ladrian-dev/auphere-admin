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
 *  ``'WA_EMBEDDED_SIGNUP'`` and ``event`` = ``'FINISH'``; we capture the
 *  WABA / phone / business ids from there. The OAuth ``code`` comes
 *  *separately* via the ``FB.login`` callback. */
export interface MetaSignupEnvelope {
  code: string;
  waba_id: string;
  phone_number_id: string;
  business_id: string;
}

const META_GRAPH_VERSION =
  process.env.NEXT_PUBLIC_META_GRAPH_API_VERSION ?? "v22.0";

/** Read-once env var with a friendly thrown error on misconfiguration —
 *  the SDK silently no-ops on bad ``appId``, so we'd rather fail loud at
 *  load time than wait for a black popup. */
function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(
      `Missing env var ${name}. Add it to Vercel + .env.local before using the Meta wizard.`,
    );
  }
  return v;
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
    const appId = requireEnv("NEXT_PUBLIC_META_APP_ID");
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
  extras?: Record<string, unknown>,
): Promise<MetaSignupEnvelope> {
  const sdk = await loadFbSdk();

  // Set up the postMessage listener BEFORE opening the popup so we can't
  // miss the event (Meta sometimes fires it before the FB.login callback
  // resolves).
  const dataPromise = new Promise<{
    waba_id: string;
    phone_number_id: string;
    business_id: string;
  }>((resolve, reject) => {
    const onMessage = (event: MessageEvent) => {
      if (!isMetaSignupMessage(event)) return;
      const data = event.data as MetaSignupMessage;
      if (data.event === "FINISH" && data.data) {
        window.removeEventListener("message", onMessage);
        resolve({
          waba_id: data.data.waba_id ?? "",
          phone_number_id: data.data.phone_number_id ?? "",
          business_id: data.data.business_id ?? "",
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
        extras: { setup: {}, ...(extras ?? {}) },
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
  event: "FINISH" | "CANCEL" | "ERROR";
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
