import { describe, expect, it } from "vitest";

import { PERMISSIONS, can } from "../permissions";

/**
 * The console's copy of the role → permission map must match the API's
 * (``core/console_auth.py``). This snapshot is the API map; if either side
 * changes, update BOTH in the same PR.
 */
const API_MAP: Record<string, string[]> = {
  "partner:read": ["owner", "admin", "builder", "analyst", "billing"],
  "clients:read": ["owner", "admin", "builder", "analyst"],
  "clients:write": ["owner", "admin", "builder"],
  "clients:delete": ["owner", "admin"],
  "agents:read": ["owner", "admin", "builder", "analyst"],
  "agents:write": ["owner", "admin", "builder"],
  "channels:read": ["owner", "admin", "builder", "analyst"],
  "channels:write": ["owner", "admin", "builder"],
  "conversations:read": ["owner", "admin", "builder", "analyst"],
  "usage:read": ["owner", "admin", "builder", "analyst", "billing"],
  "audit:read": ["owner", "admin", "analyst"],
  "team:read": ["owner", "admin", "builder", "analyst", "billing"],
  "team:manage": ["owner", "admin"],
  "keys:read": ["owner", "admin", "builder"],
  "keys:manage": ["owner", "admin"],
  "billing:read": ["owner", "billing"],
  "billing:manage": ["owner", "billing"],
};

describe("permission map", () => {
  it("matches the API map exactly", () => {
    expect(PERMISSIONS).toEqual(API_MAP);
  });
  it("admin has everything but billing; billing nothing operational", () => {
    expect(can("admin", "clients:delete")).toBe(true);
    expect(can("admin", "billing:read")).toBe(false);
    expect(can("billing", "clients:read")).toBe(false);
    expect(can("billing", "usage:read")).toBe(true);
    expect(can("analyst", "agents:write")).toBe(false);
  });
});
