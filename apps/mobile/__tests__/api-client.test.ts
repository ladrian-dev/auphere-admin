import * as SecureStore from "expo-secure-store";

import * as clientModule from "@/api/client";
import { errorOf } from "@/api/errors";

import { onSessionEvent, type SessionEvent } from "@/auth/events";
import { writeSession } from "@/auth/store";

/**
 * Spec 031 (T013, R2.1, R7.2, R13.1): the phone's way to the API.
 */
jest.mock("expo-file-system", () => ({ File: jest.fn(), Paths: {} }));
jest.mock("expo/fetch", () => ({ fetch: (...a: unknown[]) => (global.fetch as jest.Mock)(...a) }));

type Call = { url: string; headers: Headers; body?: string };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const calls: Call[] = [];
let handler: (c: Call) => Response | Promise<Response>;

beforeEach(async () => {
  calls.length = 0;
  (SecureStore as unknown as { __store: Map<string, string> }).__store.clear();
  global.fetch = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const c = { url, headers: new Headers(init?.headers ?? (input as Request).headers), body: init?.body as string | undefined };
    calls.push(c);
    return handler(c);
  }) as jest.Mock;
  await writeSession({ phoneId: "p1", accessToken: "old", accessExpiresAt: Date.now() + 30 * 60_000, refreshToken: "r1" });
});

async function client() {
  await clientModule.loadSession();
  return clientModule;
}

it("sends the credential and says which app it is", async () => {
  handler = () => json(200, { user: {} });
  const { api, call } = await client();
  await call(api.GET("/console/lite/me"));
  const sent = calls[0]!;
  expect(sent.headers.get("Authorization")).toBe("Bearer old");
  expect(sent.headers.get("X-App-Platform")).toMatch(/^(ios|android)$/);
  expect(sent.headers.get("X-App-Version")).toBeTruthy();
});

it("renews once for five requests that find the token expired, and replays all five", async () => {
  let renewals = 0;
  handler = async (c) => {
    if (c.url.endsWith("/app/phones/refresh")) {
      renewals += 1;
      await new Promise((r) => setTimeout(r, 10));
      return json(200, { access_token: "new", expires_in: 3600, refresh_token: "r2" });
    }
    return c.headers.get("Authorization") === "Bearer new" ? json(200, { ok: true }) : json(401, { detail: "expired" });
  };
  const { api, call } = await client();
  const results = await Promise.all(Array.from({ length: 5 }, () => call(api.GET("/console/lite/home"))));
  expect(renewals).toBe(1);
  expect(results).toHaveLength(5);
  expect(calls.filter((c) => c.url.endsWith("/console/lite/home") && c.headers.get("Authorization") === "Bearer new")).toHaveLength(5);
});

it("a phone_closed ends the session here and says why", async () => {
  handler = () => json(403, { detail: { code: "phone_closed", reason: "closed_by_person" } });
  const events: SessionEvent[] = [];
  const off = onSessionEvent((e) => events.push(e));
  const { api, call, hasSession } = await client();
  await expect(call(api.GET("/console/lite/home"))).rejects.toMatchObject({ status: 403, code: "phone_closed" });
  expect(events).toContainEqual({ type: "closed", reason: "closed_by_person" });
  expect(hasSession()).toBe(false);
  expect(await SecureStore.getItemAsync("session", {})).toBeNull();
  off();
});

it("a refusal on a route outside the typed client (the live line) ends the same way", async () => {
  const events: SessionEvent[] = [];
  const off = onSessionEvent((e) => events.push(e));
  const { settleRefusal, hasSession } = await client();
  await settleRefusal(json(403, { code: "phone_closed", reason: "closed_by_auphere" }));
  expect(events).toContainEqual({ type: "closed", reason: "closed_by_auphere" });
  expect(hasSession()).toBe(false);
  off();
});

it("a refused renewal is a closed phone too", async () => {
  handler = (c) =>
    c.url.endsWith("/app/phones/refresh")
      ? json(401, { detail: { code: "phone_closed", reason: "refresh_reused" } })
      : json(401, { detail: "expired" });
  const events: SessionEvent[] = [];
  const off = onSessionEvent((e) => events.push(e));
  const { api, call } = await client();
  await expect(call(api.GET("/console/lite/home"))).rejects.toMatchObject({ status: 401 });
  expect(events).toContainEqual({ type: "closed", reason: "refresh_reused" });
  off();
});

it("app_update_required sends the person to update", async () => {
  handler = () => json(403, { detail: { code: "app_update_required", minimum_version: "1.2.0", reason: "Seguridad" } });
  const events: SessionEvent[] = [];
  const off = onSessionEvent((e) => events.push(e));
  const { api, call } = await client();
  await expect(call(api.GET("/console/lite/home"))).rejects.toMatchObject({ code: "app_update_required" });
  expect(events).toContainEqual({ type: "update-required", minimum: "1.2.0", reason: "Seguridad" });
  off();
});

it("no network is an ApiError marked offline, not a crash", async () => {
  handler = () => {
    throw new TypeError("Network request failed");
  };
  const { api, call } = await client();
  await expect(call(api.GET("/console/lite/home"))).rejects.toMatchObject({ status: 0, offline: true });
});

it("reads the public routes' refusals too, which come without `detail` (`{code, …}`)", async () => {
  expect(errorOf(403, { code: "app_update_required", minimum_version: "1.2.0" })).toMatchObject({
    code: "app_update_required",
    info: { minimum_version: "1.2.0" },
  });
  expect(errorOf(401, { code: "phone_closed", reason: "refresh_reused" }).info.reason).toBe("refresh_reused");
});

it("a 401 that arrives after someone else already renewed does not renew again", async () => {
  let renewals = 0;
  let release: () => void = () => undefined;
  const late = new Promise<void>((r) => (release = r));
  handler = async (c) => {
    if (c.url.endsWith("/app/phones/refresh")) {
      renewals += 1;
      return json(200, { access_token: `new-${renewals}`, expires_in: 3600, refresh_token: `r${renewals + 1}` });
    }
    if (c.url.endsWith("/slow") && c.headers.get("Authorization") === "Bearer old") {
      await late; // answers 401 only after the other request has renewed
      return json(401, { detail: "expired" });
    }
    return c.headers.get("Authorization") === "Bearer old" ? json(401, { detail: "expired" }) : json(200, { ok: true });
  };
  const { authedFetch } = await client();
  const slow = authedFetch("http://api/slow");
  await authedFetch("http://api/fast"); // 401 → renews once → 200
  release();
  const res = await slow;
  expect(res.status).toBe(200);
  expect(renewals).toBe(1);
});
