/**
 * Spec 047 (T201, 58.5): the panel's client of `/admin/builder/sector-guides`
 * and `/admin/builder/generated-guides`, against
 * `contracts/admin-sector-guides.md`, with the API simulated by `fetch`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { BackendError } = await import("@/lib/backend");
const { sectorGuidesBackend } = await import("@/lib/backend-sector-guides");

type Sent = { url: string; method: string; headers: Record<string, string>; body: unknown };

const sent: Sent[] = [];
let reply: { status: number; body: unknown } = { status: 200, body: {} };

beforeEach(() => {
  sent.length = 0;
  reply = { status: 200, body: {} };
  vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    sent.push({
      url,
      method: init.method ?? "GET",
      headers: init.headers as Record<string, string>,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
    });
    const text = reply.body === undefined ? "" : JSON.stringify(reply.body);
    return new Response(text, { status: reply.status, headers: { "Content-Type": "application/json" } });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const TENANT = "aaaaaaaa-0000-0000-0000-000000000001";
const GUIDE = "bbbbbbbb-0000-0000-0000-000000000002";
const OPERATOR = "cccccccc-0000-0000-0000-000000000003";
const BASE = `/admin/builder/generated-guides/${TENANT}/${GUIDE}`;

function only(): Sent {
  expect(sent).toHaveLength(1);
  return sent[0]!;
}

describe("the sector guides client (contracts/admin-sector-guides.md)", () => {
  it("reads Auphere's guides with the panel's token and nothing else", async () => {
    reply = { status: 200, body: { items: [] } };
    expect(await sectorGuidesBackend.guides()).toEqual({ items: [] });
    const req = only();
    expect(req.method).toBe("GET");
    expect(new URL(req.url).pathname).toBe("/admin/builder/sector-guides");
    expect(req.headers.Authorization).toMatch(/^Bearer .+/);
    expect(req.headers["X-Operator-Id"]).toBeUndefined();
  });

  it("asks for the missing labels with the limit it is given", async () => {
    reply = { status: 200, body: { items: [], clients_scanned: 0, generated_at: "2026-10-30T10:00:00+00:00" } };
    await sectorGuidesBackend.missing(20);
    const url = new URL(only().url);
    expect(url.pathname).toBe("/admin/builder/sector-guides/missing");
    expect(url.searchParams.get("limit")).toBe("20");
  });

  it("reads one generated guide by its client and its id, and says null when it is not that client's", async () => {
    reply = { status: 200, body: { guide_id: GUIDE } };
    expect(await sectorGuidesBackend.generated(TENANT, GUIDE)).toEqual({ guide_id: GUIDE });
    expect(new URL(only().url).pathname).toBe(BASE);

    sent.length = 0;
    reply = { status: 404, body: { detail: { code: "unknown_guide" } } };
    expect(await sectorGuidesBackend.generated(TENANT, GUIDE)).toBeNull();
  });

  it("never lets an id change the route", async () => {
    reply = { status: 200, body: {} };
    await sectorGuidesBackend.generated("../x", "y?z");
    expect(only().url).toContain("/admin/builder/generated-guides/..%2Fx/y%3Fz");
  });

  it("reviews with the operator and only the fields it is given", async () => {
    reply = { status: 200, body: { status: "reviewed" } };
    await sectorGuidesBackend.review(TENANT, GUIDE, { note: "Quitado el teléfono del paso 2" }, OPERATOR);
    const req = only();
    expect(req.method).toBe("POST");
    expect(new URL(req.url).pathname).toBe(`${BASE}/review`);
    expect(req.headers["X-Operator-Id"]).toBe(OPERATOR);
    expect(req.headers["Content-Type"]).toBe("application/json");
    expect(req.body).toEqual({ note: "Quitado el teléfono del paso 2" });
  });

  it("promotes with {key, label, reason} and the operator", async () => {
    reply = { status: 201, body: { key: "gimnasio", source: "promoted", version: 1 } };
    const body = { key: "gimnasio", label: "Gimnasio", reason: "Siete clientes, revisada por Ana" };
    expect(await sectorGuidesBackend.promote(TENANT, GUIDE, body, OPERATOR)).toMatchObject({ key: "gimnasio" });
    const req = only();
    expect(req.method).toBe("POST");
    expect(new URL(req.url).pathname).toBe(`${BASE}/promote`);
    expect(req.headers["X-Operator-Id"]).toBe(OPERATOR);
    expect(req.body).toEqual(body);
  });

  it("keeps the API's refusal, findings included, for the screen to say", async () => {
    const detail = {
      code: "client_data_found",
      findings: [{ pointer: "/guide/procedures/0/steps", kind: "phone", excerpt: "…llama al 612 345 678…" }],
    };
    reply = { status: 422, body: { detail } };
    const error = await sectorGuidesBackend.review(TENANT, GUIDE, {}, OPERATOR).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(BackendError);
    expect((error as InstanceType<typeof BackendError>).status).toBe(422);
    expect((error as InstanceType<typeof BackendError>).body).toEqual({ detail });
  });
});
