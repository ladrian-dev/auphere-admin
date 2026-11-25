import type { paths } from "../schema.gen";

/**
 * The plumbing of the example API (spec 069, Requisito 23): what a request
 * looks like once it reaches `demoFetch`, the answers it can give, and a route
 * table whose bodies are typed from the API's own OpenAPI (`schema.gen.ts`).
 * A route declares its path as the schema writes it and the success status
 * the schema declares; its handler can only return that status's body.
 */

// ── types from the schema ─────────────────────────────────────────────

export type Method = "get" | "post" | "put" | "patch" | "delete";
export type Path = keyof paths;

type Op<P extends Path, M extends Method> = paths[P][M];
type Responses<O> = O extends { responses: infer R } ? R : never;

/** The success statuses an operation declares (200, 201, 202 or 204). */
export type OkStatus<P extends Path, M extends Method> = Extract<keyof Responses<Op<P, M>>, 200 | 201 | 202 | 204>;

type Json<R> = R extends { content: { "application/json": infer B } } ? B : null;
type BodyAt<O, St> = O extends { responses: infer R } ? (St extends keyof R ? Json<R[St]> : never) : never;

/** What the schema says a route answers on `St`: its JSON body, or `null` when it has none (204). */
export type OkBody<P extends Path, M extends Method, St extends OkStatus<P, M>> = BodyAt<Op<P, M>, St>;

type RequestBodyOf<O> = O extends { requestBody?: infer R } ? NonNullable<R> : never;

/** The JSON a route takes, when it takes JSON (`never` for none or for multipart). */
export type InBody<P extends Path, M extends Method> = RequestBodyOf<Op<P, M>> extends { content: { "application/json": infer B } } ? B : never;

/** `{conversation_id}` and friends, as named in the path. */
type ParamNames<P extends string> = P extends `${string}{${infer K}}${infer Rest}` ? K | ParamNames<Rest> : never;
export type Params<P extends string> = { [K in ParamNames<P>]: string };

// ── the request ───────────────────────────────────────────────────────

export type DemoRequest = {
  method: string;
  /** Without the origin and the query: `/console/lite/home`. */
  path: string;
  /** The first value of each query parameter. */
  query: Record<string, string | undefined>;
  headers: Headers;
  /** The parsed JSON, the `FormData` of an upload (never read), or `null`. */
  body: unknown;
};

const ORIGIN = /^[a-z][a-z0-9+.-]*:\/\/[^/?#]*/i;

function decode(s: string): string {
  try {
    return decodeURIComponent(s.replace(/\+/g, " "));
  } catch {
    return s;
  }
}

function parseJson(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/** Split a URL by hand: React Native's `URL` has no `searchParams` in every version. */
export function splitUrl(url: string): { path: string; query: Record<string, string | undefined> } {
  const rest = url.replace(ORIGIN, "").split("#")[0] ?? "";
  const at = rest.indexOf("?");
  const path = (at >= 0 ? rest.slice(0, at) : rest) || "/";
  const query: Record<string, string | undefined> = {};
  if (at >= 0) {
    for (const pair of rest.slice(at + 1).split("&")) {
      if (!pair) continue;
      const eq = pair.indexOf("=");
      const key = decode(eq >= 0 ? pair.slice(0, eq) : pair);
      if (!(key in query)) query[key] = eq >= 0 ? decode(pair.slice(eq + 1)) : "";
    }
  }
  return { path: path.length > 1 ? path.replace(/\/+$/, "") : path, query };
}

/**
 * The three ways the app calls: a `Request` (openapi-fetch), a URL with a
 * string body (`authedFetch`, the renewal, Reservas) and a URL with a
 * `FormData` body (an upload, which is never parsed).
 */
export async function readRequest(input: Request | string, init?: RequestInit): Promise<DemoRequest> {
  const req = typeof input === "string" ? null : input;
  const url = req ? req.url : (input as string);
  const method = (init?.method ?? req?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers ?? req?.headers ?? undefined);
  let body: unknown = null;
  const raw: unknown = init?.body;
  if (typeof raw === "string") body = parseJson(raw);
  // An upload's `FormData` (React Native's own has no `get`): kept as it came, never read here.
  else if (raw != null && typeof raw === "object") body = raw;
  else if (raw == null && req && method !== "GET" && method !== "HEAD") body = parseJson(await req.text().catch(() => ""));
  return { method, ...splitUrl(url), headers, body };
}

// ── the answers ───────────────────────────────────────────────────────

/** A refusal, with the API's body. Thrown by a handler; the router answers it. */
export class DemoHttpError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`demo ${status}`);
    this.name = "DemoHttpError";
    this.status = status;
    this.body = body;
  }
}

/** A console route's refusal: FastAPI's `{"detail": {"code": …}}`. */
export function refuse(status: number, code: string, info: Record<string, unknown> = {}): DemoHttpError {
  return new DemoHttpError(status, { detail: { code, ...info } });
}

/** A public `/app/*` refusal: the code at the top level (`api/app_public.py`, `_code`). */
export function refusePublic(status: number, code: string, info: Record<string, unknown> = {}): DemoHttpError {
  return new DemoHttpError(status, { code, ...info });
}

export function notFound(what = "not_found"): DemoHttpError {
  return refuse(404, what);
}

/** A JSON answer; 204, and a 202 without a body, go empty, as the API sends them. */
export function respond(status: number, body: unknown): Response {
  if (status === 204 || (status === 202 && body == null)) return new Response(null, { status, headers: { "Content-Length": "0" } });
  return new Response(JSON.stringify(body ?? null), { status, headers: { "Content-Type": "application/json" } });
}

/** `If-Match: 7` or `If-Match: "7"` → 7; anything else → `null`. */
export function ifMatch(headers: Headers): number | null {
  const raw = headers.get("If-Match");
  if (raw == null) return null;
  const n = Number(raw.trim().replace(/^W\//, "").replace(/^"|"$/g, ""));
  return Number.isInteger(n) ? n : null;
}

export function pause(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 150–350 ms: long enough for a skeleton to show, short enough to use. */
export function latency(): number {
  return 150 + Math.floor(Math.random() * 201);
}

// ── the route table ───────────────────────────────────────────────────

export type Context<P extends Path, M extends Method> = DemoRequest & {
  params: Params<P & string>;
  /** The request's JSON as the schema types it (the app's own calls; nothing else reaches here). */
  json: InBody<P, M> | null;
};

export type Route = {
  method: Uppercase<Method>;
  path: Path;
  status: number;
  /** Reservas waits inside its own example source; everything else waits here. */
  wait: boolean;
  handle: (req: DemoRequest, params: Record<string, string>) => Promise<unknown>;
};

/**
 * One route: the schema's path, its method, the success status it declares
 * and a handler that can only return that status's body. A handler without
 * parameters is checked before the path's types are known, so one that
 * returns a literal union (`kind: "waiting"`) names its body type itself.
 */
export function route<P extends Path, M extends Method, St extends OkStatus<P, M>>(
  method: M,
  path: P,
  status: St,
  handler: (ctx: Context<P, M>) => OkBody<P, M, St> | Promise<OkBody<P, M, St>>,
  options: { wait?: boolean } = {},
): Route {
  return {
    method: method.toUpperCase() as Uppercase<Method>,
    path,
    status: status as number,
    wait: options.wait ?? true,
    handle: async (req, params) => {
      const json = isJson(req.body) ? (req.body as InBody<P, M>) : null;
      return handler({ ...req, params: params as Params<P & string>, json });
    },
  };
}

/** What `JSON.parse` makes: a plain object or an array (a `FormData` is neither). */
function isJson(v: unknown): boolean {
  if (Array.isArray(v)) return true;
  if (!v || typeof v !== "object") return false;
  const proto: unknown = Object.getPrototypeOf(v);
  return proto === Object.prototype || proto === null;
}

/** The route for a request, preferring the one with more fixed segments (`/inbox/counts` over `/inbox/{id}`). */
export function match(routes: readonly Route[], method: string, path: string): { route: Route; params: Record<string, string> } | null {
  const parts = path.split("/").filter(Boolean).map(decode);
  let best: { route: Route; params: Record<string, string>; fixed: number } | null = null;
  for (const r of routes) {
    if (r.method !== method) continue;
    const pattern = r.path.split("/").filter(Boolean);
    if (pattern.length !== parts.length) continue;
    const params: Record<string, string> = {};
    let fixed = 0;
    let ok = true;
    for (let i = 0; i < pattern.length && ok; i++) {
      const p = pattern[i] ?? "";
      const v = parts[i] ?? "";
      if (p.startsWith("{") && p.endsWith("}")) params[p.slice(1, -1)] = v;
      else if (p === v) fixed += 1;
      else ok = false;
    }
    if (ok && (!best || fixed > best.fixed)) best = { route: r, params, fixed };
  }
  return best ? { route: best.route, params: best.params } : null;
}
