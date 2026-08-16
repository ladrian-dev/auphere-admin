/**
 * Facebook JS SDK loader + Embedded Signup helper for the console (CP-17).
 *
 * Same protocol as `apps/admin/src/lib/meta-fb-sdk.ts` (the OAuth `code`
 * arrives through the `FB.login` callback, the WABA / phone ids through a
 * `postMessage` from the popup; both are needed) but written for this app:
 * app id / graph version / config ids come in as ARGUMENTS from the server
 * component (`env()`), never from `NEXT_PUBLIC_*`, and errors are codes the
 * caller translates (ES/EN) instead of Spanish strings.
 *
 * Browser only. The script tag is created by a nonce'd bundle, which the
 * console CSP (`'strict-dynamic'`) trusts; `connect.facebook.net` is also
 * listed explicitly in `proxy.ts`.
 */

/** Exact origins Meta posts Embedded Signup messages from — never a suffix match. */
const META_ORIGINS = new Set(["https://www.facebook.com", "https://web.facebook.com", "https://business.facebook.com"]);

declare global {
  interface Window {
    FB?: FbSdk;
    fbAsyncInit?: () => void;
  }
}

interface FbSdk {
  init(opts: { appId: string; version: string; xfbml?: boolean; cookie?: boolean }): void;
  login(
    cb: (response: FbLoginResponse) => void,
    opts: {
      config_id: string;
      response_type: "code";
      override_default_response_type?: boolean;
      extras?: Record<string, unknown>;
    },
  ): void;
}

interface FbLoginResponse {
  authResponse?: { code?: string };
  status?: string;
}

export type SignupMode = "cloud_api" | "coexistence";

export type MetaSignupEnvelope = {
  code: string;
  waba_id: string;
  phone_number_id?: string;
  business_id?: string;
};

export type SignupErrorCode = "sdk_failed" | "cancelled" | "timeout" | "no_code" | "meta_error";

export class SignupError extends Error {
  constructor(
    public readonly code: SignupErrorCode,
    detail?: string,
  ) {
    super(detail ?? code);
    this.name = "SignupError";
  }
}

let sdkPromise: Promise<FbSdk> | null = null;

export function loadFbSdk(appId: string, version: string): Promise<FbSdk> {
  if (typeof window === "undefined") return Promise.reject(new SignupError("sdk_failed", "no window"));
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<FbSdk>((resolve, reject) => {
    if (window.FB) {
      window.FB.init({ appId, version });
      resolve(window.FB);
      return;
    }
    window.fbAsyncInit = () => {
      try {
        window.FB!.init({ appId, version });
        resolve(window.FB!);
      } catch (err) {
        reject(new SignupError("sdk_failed", String(err)));
      }
    };
    const script = document.createElement("script");
    script.async = true;
    script.defer = true;
    script.crossOrigin = "anonymous";
    script.src = "https://connect.facebook.net/en_US/sdk.js";
    script.onerror = () => {
      sdkPromise = null;
      reject(new SignupError("sdk_failed"));
    };
    document.body.appendChild(script);
  });
  return sdkPromise;
}

type MetaSignupMessage = {
  type: "WA_EMBEDDED_SIGNUP";
  event: "FINISH" | "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING" | "CANCEL" | "ERROR";
  data?: { waba_id?: string; phone_number_id?: string; business_id?: string; error_message?: string };
};

/** Meta posts the envelope as a JSON string; tolerate an object. Pure, tested. */
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
  if ((parsed as { type?: unknown }).type !== "WA_EMBEDDED_SIGNUP") return null;
  return parsed as MetaSignupMessage;
}

/** `featureType` is what tells Meta which wizard to render. */
export function loginExtras(mode: SignupMode): Record<string, unknown> {
  return {
    setup: {},
    featureType: mode === "coexistence" ? "whatsapp_business_app_onboarding" : "",
    sessionInfoVersion: "3",
  };
}

const TIMEOUT_MS = 5 * 60 * 1000;

export async function loginWithMeta(opts: {
  appId: string;
  version: string;
  configId: string;
  mode: SignupMode;
}): Promise<MetaSignupEnvelope> {
  const sdk = await loadFbSdk(opts.appId, opts.version);

  const dataPromise = new Promise<Omit<MetaSignupEnvelope, "code">>((resolve, reject) => {
    const timer = setTimeout(() => {
      window.removeEventListener("message", onMessage);
      reject(new SignupError("timeout"));
    }, TIMEOUT_MS);
    function onMessage(event: MessageEvent) {
      if (typeof event.origin !== "string" || !META_ORIGINS.has(event.origin)) return;
      const data = parseMetaSignupMessage(event.data);
      if (data === null) return;
      const finished = data.event === "FINISH" || data.event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING";
      if (finished && data.data) {
        window.removeEventListener("message", onMessage);
        clearTimeout(timer);
        if (!data.data.waba_id) return reject(new SignupError("meta_error", "FINISH without waba_id"));
        resolve({
          waba_id: data.data.waba_id,
          phone_number_id: data.data.phone_number_id || undefined,
          business_id: data.data.business_id || undefined,
        });
      } else if (data.event === "CANCEL" || data.event === "ERROR") {
        window.removeEventListener("message", onMessage);
        clearTimeout(timer);
        reject(data.event === "CANCEL" ? new SignupError("cancelled") : new SignupError("meta_error", data.data?.error_message));
      }
    }
    window.addEventListener("message", onMessage);
  });

  const codePromise = new Promise<string>((resolve, reject) => {
    sdk.login(
      (response) => {
        if (response.authResponse?.code) resolve(response.authResponse.code);
        else reject(new SignupError(response.status === "not_authorized" ? "cancelled" : "no_code"));
      },
      { config_id: opts.configId, response_type: "code", override_default_response_type: true, extras: loginExtras(opts.mode) },
    );
  });

  const [code, data] = await Promise.all([codePromise, dataPromise]);
  return { code, ...data };
}
