/**
 * Typed client for the FastAPI ``/qa/*`` surface (ADR-020 Phase 3+5).
 *
 * Separated from ``backend.ts`` because every QA request needs an
 * ``X-Operator-Id`` header on top of the admin Bearer — the API uses
 * that to enforce RLS on ``qa.*`` rows. Better Auth (Block G) will
 * eventually derive the operator id from the session; until then we
 * pass it explicitly from the caller.
 *
 * Server-side only. The bearer must not reach the browser.
 */

import "server-only";

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://localhost:8000";
const ADMIN_TOKEN =
  process.env.NEXUS_ADMIN_TOKEN ?? "dev-admin-token-change-me";

export class QAApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly url: string,
    public readonly body: unknown,
  ) {
    super(
      `qa-api ${status} ${url}: ${
        typeof body === "string"
          ? body.slice(0, 200)
          : JSON.stringify(body).slice(0, 200)
      }`,
    );
  }
}

type QAFetchOpts = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** When ``true``, 404 yields ``null`` instead of throwing. */
  optional?: boolean;
};

async function qaCall<T>(
  path: string,
  operatorId: string,
  opts: QAFetchOpts = {},
): Promise<T | null> {
  const url = `${BACKEND_URL}${path}`;
  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: {
      Authorization: `Bearer ${ADMIN_TOKEN}`,
      "X-Operator-Id": operatorId,
      Accept: "application/json",
      ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    cache: "no-store",
    signal: opts.signal,
  };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
  const res = await fetch(url, init);
  if (res.status === 404 && opts.optional) return null;
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!res.ok) throw new QAApiError(res.status, url, parsed);
  return parsed as T;
}

// ── domain types (mirror apps/api/src/nexus_api/api/qa.py) ──────────────────

export type QAThread = {
  id: string;
  tenant_id: string;
  operator_id: string;
  external_id: string | null;
  title: string;
  archived_at: string | null;
  last_run_at: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type QAThreadCreateInput = {
  tenant_id: string;
  title?: string;
};

export type QAThreadPatchInput = {
  title?: string;
  archived?: boolean;
};

export type QASideEffectAudit = {
  id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  synthetic_result: Record<string, unknown>;
  blocked_reason: string;
  run_id: string | null;
  created_at: string;
};

// ── client (one method per endpoint) ────────────────────────────────────────

export const qaApi = {
  async listThreads(opts: {
    operatorId: string;
    tenantId?: string;
    includeArchived?: boolean;
    limit?: number;
    signal?: AbortSignal;
  }): Promise<QAThread[]> {
    const params = new URLSearchParams();
    if (opts.tenantId) params.set("tenant_id", opts.tenantId);
    if (opts.includeArchived) params.set("include_archived", "true");
    if (opts.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    const path = `/qa/threads${qs ? `?${qs}` : ""}`;
    const r = await qaCall<QAThread[]>(path, opts.operatorId, {
      signal: opts.signal,
    });
    return r ?? [];
  },

  async createThread(opts: {
    operatorId: string;
    input: QAThreadCreateInput;
    signal?: AbortSignal;
  }): Promise<QAThread> {
    const r = await qaCall<QAThread>("/qa/threads", opts.operatorId, {
      method: "POST",
      body: opts.input,
      signal: opts.signal,
    });
    if (!r) throw new Error("qa-api returned null for createThread");
    return r;
  },

  async getThread(opts: {
    operatorId: string;
    threadId: string;
    signal?: AbortSignal;
  }): Promise<QAThread | null> {
    return qaCall<QAThread>(
      `/qa/threads/${opts.threadId}`,
      opts.operatorId,
      { signal: opts.signal, optional: true },
    );
  },

  async patchThread(opts: {
    operatorId: string;
    threadId: string;
    input: QAThreadPatchInput;
    signal?: AbortSignal;
  }): Promise<QAThread> {
    const r = await qaCall<QAThread>(
      `/qa/threads/${opts.threadId}`,
      opts.operatorId,
      { method: "PATCH", body: opts.input, signal: opts.signal },
    );
    if (!r) throw new Error("qa-api returned null for patchThread");
    return r;
  },

  async getThreadAudit(opts: {
    operatorId: string;
    threadId: string;
    limit?: number;
    signal?: AbortSignal;
  }): Promise<QASideEffectAudit[]> {
    const params = new URLSearchParams();
    if (opts.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    const path = `/qa/threads/${opts.threadId}/audit${qs ? `?${qs}` : ""}`;
    const r = await qaCall<QASideEffectAudit[]>(path, opts.operatorId, {
      signal: opts.signal,
    });
    return r ?? [];
  },
};

