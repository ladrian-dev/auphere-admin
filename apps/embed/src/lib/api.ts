/**
 * Typed client for `/v1/embed/*` (ADR-028). Bearer = the widget session
 * JWT from the bridge (memory only). On 401 we ask the loader for a
 * fresh token and the UI retries.
 */

import { getToken, postToParent } from "./bridge";

const API_BASE = process.env.NEXT_PUBLIC_NEXUS_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  if (!token) throw new ApiError(401, "no session token yet");
  const response = await fetch(`${API_BASE}/v1/embed${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (response.status === 401) {
    // Token expired mid-flow — ask the loader to re-mint; the caller
    // surfaces a retryable error state.
    postToParent("auph:token:expiring");
    throw new ApiError(401, "session expired, refreshing");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export interface TemplateComponent {
  type: string;
  text?: string;
  [key: string]: unknown;
}

export interface Template {
  id: string | null;
  name: string;
  language: string;
  category: string | null;
  status: string | null;
  components: TemplateComponent[];
}

export interface BroadcastAccepted {
  broadcast_id: string;
  accepted: number;
  rejected: { phone: string; reason: string }[];
}

export interface BroadcastStatus {
  broadcast_id: string;
  template_name: string;
  status: string;
  counts: Record<string, number>;
  recipients: { phone: string; status: string; reason: string | null }[];
}

export function fetchStatus() {
  return request<{ status: "connected" | "not_connected"; display_phone_number: string | null }>(
    "/status",
  );
}

export function fetchTemplates() {
  return request<{ templates: Template[] }>("/templates");
}

export function createBroadcast(body: {
  template_name: string;
  language: string;
  recipients: { phone: string; variables: Record<string, string> }[];
  idempotency_key?: string;
}) {
  return request<BroadcastAccepted>("/broadcasts", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchBroadcast(id: string) {
  return request<BroadcastStatus>(`/broadcasts/${id}`);
}

export interface SignupResult {
  status: "connected";
  display_phone_number: string;
  tenant_activated: boolean;
}

/** Complete Meta Embedded Signup with the envelope from `FB.login` +
 * the popup's postMessage. Requires the `widget:connect` scope. */
export function completeSignup(body: {
  code: string;
  waba_id: string;
  phone_number_id?: string;
  business_id?: string;
  mode?: "cloud_api" | "coexistence";
}) {
  return request<SignupResult>("/whatsapp/signup", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Named `{{variables}}` of the template's BODY component. */
export function templateBodyVars(template: Template): string[] {
  const body = template.components.find((c) => c.type?.toUpperCase() === "BODY");
  if (!body?.text) return [];
  return [...body.text.matchAll(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g)].map((m) => m[1]!);
}

/** Render a template body with a recipient's variables, for the preview. */
export function renderPreview(template: Template, variables: Record<string, string>): string {
  const body = template.components.find((c) => c.type?.toUpperCase() === "BODY");
  if (!body?.text) return "";
  return body.text.replace(
    /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g,
    (_match, name: string) => variables[name] ?? `{{${name}}}`,
  );
}
