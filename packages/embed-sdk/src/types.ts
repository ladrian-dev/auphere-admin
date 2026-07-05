/**
 * Public types for `@auphere/embed` (ADR-028).
 *
 * The SDK is a thin loader: it renders nothing itself beyond an iframe
 * overlay, and it never sees WhatsApp or Auphere credentials. All the
 * heavy UI lives on the Auphere-controlled embed origin and is updated
 * without you redeploying.
 */

/** One WhatsApp recipient of a broadcast, with the named template variables. */
export interface BroadcastRecipient {
  /** E.164 phone, e.g. `+56912345678`. Spaces/dashes are tolerated. */
  phone: string;
  /**
   * Named template variables, keys matching the template's named
   * parameters (e.g. `{ cliente: "Ana", saldo_pendiente: "$12.000" }`).
   */
  variables?: Record<string, string>;
}

/** What your backend returns after minting `POST /v1/widget-sessions`. */
export interface WidgetSession {
  /** The short-lived session JWT (`session_token` from the mint response). */
  sessionToken: string;
  /** Seconds until expiry (`expires_in`). */
  expiresIn?: number;
  /** Connection state included in the mint response. */
  whatsapp?: {
    status: "connected" | "not_connected";
    displayPhoneNumber?: string | null;
  };
}

/** Raw mint response shape (snake_case) is also accepted. */
export interface WidgetSessionWire {
  session_token: string;
  expires_in?: number;
  whatsapp?: {
    status: "connected" | "not_connected";
    display_phone_number?: string | null;
  };
}

export type FetchSession = () => Promise<WidgetSession | WidgetSessionWire>;

export interface Appearance {
  /** Primary accent color (CSS color). */
  colorPrimary?: string;
  /** Border radius, e.g. `"8px"`. */
  radius?: string;
  /** `"light" | "dark"` — defaults to the embedding page's scheme. */
  theme?: "light" | "dark";
}

export interface AuphereConfig {
  /**
   * Called whenever the SDK needs a session token: on open and again
   * when a token is about to expire. MUST be re-invocable without user
   * interaction — typically a `fetch("/api/auphere/session")` to your
   * backend, which mints with your secret key.
   */
  fetchSession: FetchSession;
  /**
   * Your partner slug (shown in the Auphere dashboard). Used to resolve
   * the iframe's security policy before any token exists.
   */
  partnerSlug: string;
  appearance?: Appearance;
  /** BCP-47, e.g. `"es"`. Defaults to the page language. */
  locale?: string;
  /** Override the embed origin — staging/dev only. */
  embedOrigin?: string;
}

export type ConnectionStatus = "connected" | "not_connected" | "unknown";

export interface OpenBroadcastOptions {
  /** The audience, built from YOUR data. The modal previews and sends — it never invents recipients. */
  recipients: BroadcastRecipient[];
  /** Fired after the broadcast is accepted by Auphere. */
  onDone?: (result: { broadcastId: string; accepted: number }) => void;
  /** Fired when the modal closes (sent or not). */
  onExit?: () => void;
}

export interface ConnectWhatsAppOptions {
  onConnected?: (info: { displayPhoneNumber: string | null }) => void;
  onExit?: () => void;
}

export interface Auphere {
  /** Last known WhatsApp connection state (from the latest session mint/refresh). */
  getStatus(): ConnectionStatus;
  /** Re-mint a session and refresh the status. */
  refreshStatus(): Promise<ConnectionStatus>;
  /** Subscribe to status flips. Returns an unsubscribe function. */
  onStatusChange(listener: (status: ConnectionStatus) => void): () => void;
  /** Open the broadcast modal (fullscreen iframe overlay). */
  openBroadcast(options: OpenBroadcastOptions): Promise<void>;
  /** Open the WhatsApp Embedded Signup flow (fullscreen iframe overlay). */
  connectWhatsApp(options?: ConnectWhatsAppOptions): Promise<void>;
  /** Remove any mounted iframe and listeners. */
  destroy(): void;
}
