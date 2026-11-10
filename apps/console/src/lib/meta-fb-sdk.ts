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

export type SignupErrorCode = "sdk_failed" | "cancelled" | "timeout" | "no_code" | "meta_error" | "no_number" | "grant_only";

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

/**
 * Embedded Signup version (spec 050, D3). v4 is what Meta supports today;
 * v5 (coexistence on by default, `FINISH` without `waba_id`) sits behind
 * `meta_embedded_signup_version` until the five paths pass in staging.
 */
export type SignupVersion = "v4" | "v5";

type MetaSignupMessage = {
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
    /** v5: the WABA comes here instead of `waba_id`. */
    messaging_account_ids?: string[] | string;
    error_message?: string;
    current_step?: string;
  };
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

/** How a signup message ends the wait: the WABA ids, or why not. */
export type SignupOutcome =
  | { kind: "finished"; waba_id: string; phone_number_id?: string; business_id?: string }
  | { kind: "failed"; code: SignupErrorCode; detail?: string };

function firstId(ids: string[] | string | undefined): string | undefined {
  const id = Array.isArray(ids) ? ids[0] : ids;
  return typeof id === "string" && id ? id : undefined;
}

/**
 * Pure: what a parsed message means, or `null` while the wizard is still
 * open. `FINISH_ONLY_WABA` and `FINISH_GRANT_ONLY_API_ACCESS` end without a
 * number to connect: they say what is missing instead of failing mute.
 */
export function signupOutcome(msg: MetaSignupMessage | null): SignupOutcome | null {
  if (msg === null) return null;
  const data = msg.data ?? {};
  switch (msg.event) {
    case "FINISH":
    case "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING": {
      const waba = data.waba_id || firstId(data.messaging_account_ids);
      if (!waba) return { kind: "failed", code: "meta_error", detail: `${msg.event} without waba_id` };
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
 * The `extras` of `FB.login`, which tell Meta which wizard to render.
 *
 * v4: coexistence is `featureType`; Cloud API sends nothing else. No
 * `sessionInfoVersion`: Meta retired it with v4.
 * v5: coexistence is on by default, so Cloud API turns it off.
 */
export function signupExtras(mode: SignupMode, version: SignupVersion = "v4"): Record<string, unknown> {
  if (version === "v5") {
    return mode === "coexistence"
      ? { version: "v5" }
      : { version: "v5", features: [{ name: "whatsapp_business_app_onboarding", enabled: false }] };
  }
  return mode === "coexistence" ? { setup: {}, featureType: "whatsapp_business_app_onboarding" } : { setup: {} };
}

const TIMEOUT_MS = 5 * 60 * 1000;

/** Meta's Embedded Signup lays itself out for ~630px; this leaves a margin. */
export const META_POPUP = { width: 720, height: 780 } as const;

/**
 * Pure: window features that put a popup of `size` in the middle of `screen`.
 *
 * The SDK opens the dialog with `window.open` and its own features, and
 * Chrome answered them with a window the size of the whole screen, Meta's
 * wizard huddled in its top-left corner. `popup=yes` is what tells the
 * browser this is a dialog and not a tab.
 */
export function centeredPopupFeatures(
  screen: { width: number; height: number; left?: number; top?: number },
  size: { width: number; height: number } = META_POPUP,
): string {
  const width = Math.min(size.width, screen.width);
  const height = Math.min(size.height, screen.height);
  const left = Math.max(0, Math.round((screen.left ?? 0) + (screen.width - width) / 2));
  const top = Math.max(0, Math.round((screen.top ?? 0) + (screen.height - height) / 2));
  return `popup=yes,width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`;
}

/** Drop from Meta's features the keys ours override; keep the rest. */
function mergeFeatures(theirs: string | undefined, ours: string): string {
  const overridden = new Set(["popup", "width", "height", "left", "top"]);
  const kept = (theirs ?? "")
    .split(",")
    .map((f) => f.trim())
    .filter((f) => f && !overridden.has(f.split("=")[0]!.trim().toLowerCase()));
  return [ours, ...kept].join(",");
}

/**
 * Run `fn` with `window.open` centring whatever it opens, then put
 * `window.open` back — whether `fn` returns or throws. The SDK opens the
 * popup synchronously inside `FB.login` (it has to, to stay inside the
 * click), so the patch only needs to live that long.
 */
export function withCenteredPopup<T>(fn: () => T): T {
  if (typeof window === "undefined") return fn();
  const original = window.open;
  const features = centeredPopupFeatures({
    width: window.screen?.availWidth || window.innerWidth,
    height: window.screen?.availHeight || window.innerHeight,
    left: (window.screen as { availLeft?: number } | undefined)?.availLeft ?? 0,
    top: (window.screen as { availTop?: number } | undefined)?.availTop ?? 0,
  });
  window.open = ((url?: string | URL, target?: string, theirs?: string) =>
    original.call(window, url, target, mergeFeatures(theirs, features))) as typeof window.open;
  try {
    return fn();
  } finally {
    window.open = original;
  }
}

export async function loginWithMeta(opts: {
  appId: string;
  version: string;
  configId: string;
  mode: SignupMode;
  signupVersion?: SignupVersion;
}): Promise<MetaSignupEnvelope> {
  const sdk = await loadFbSdk(opts.appId, opts.version);

  const dataPromise = new Promise<Omit<MetaSignupEnvelope, "code">>((resolve, reject) => {
    const timer = setTimeout(() => {
      window.removeEventListener("message", onMessage);
      reject(new SignupError("timeout"));
    }, TIMEOUT_MS);
    function onMessage(event: MessageEvent) {
      if (typeof event.origin !== "string" || !META_ORIGINS.has(event.origin)) return;
      const outcome = signupOutcome(parseMetaSignupMessage(event.data));
      if (outcome === null) return;
      window.removeEventListener("message", onMessage);
      clearTimeout(timer);
      if (outcome.kind === "failed") return reject(new SignupError(outcome.code, outcome.detail));
      resolve({ waba_id: outcome.waba_id, phone_number_id: outcome.phone_number_id, business_id: outcome.business_id });
    }
    window.addEventListener("message", onMessage);
  });

  const codePromise = new Promise<string>((resolve, reject) => {
    withCenteredPopup(() =>
      sdk.login(
        (response) => {
          if (response.authResponse?.code) resolve(response.authResponse.code);
          else reject(new SignupError(response.status === "not_authorized" ? "cancelled" : "no_code"));
        },
        { config_id: opts.configId, response_type: "code", override_default_response_type: true, extras: signupExtras(opts.mode, opts.signupVersion) },
      ),
    );
  });

  const [code, data] = await Promise.all([codePromise, dataPromise]);
  return { code, ...data };
}

/**
 * Spec 049 — Facebook Login for Business for Instagram (Unified Login) and
 * Messenger. Same popup, same `config_id` + `response_type=code` as the
 * WhatsApp signup, but no `WA_EMBEDDED_SIGNUP` message: what the business
 * granted is read by the server after it exchanges the code. Resolves with
 * the single-use code.
 */
export async function loginForCode(opts: { appId: string; version: string; configId: string }): Promise<string> {
  const sdk = await loadFbSdk(opts.appId, opts.version);
  return new Promise<string>((resolve, reject) => {
    const timer = setTimeout(() => reject(new SignupError("timeout")), TIMEOUT_MS);
    withCenteredPopup(() =>
      sdk.login(
        (response) => {
          clearTimeout(timer);
          if (response.authResponse?.code) resolve(response.authResponse.code);
          else reject(new SignupError(response.status === "not_authorized" ? "cancelled" : "no_code"));
        },
        { config_id: opts.configId, response_type: "code", override_default_response_type: true },
      ),
    );
  });
}
