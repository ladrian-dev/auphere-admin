/**
 * Spec 079, requisito 1: the panel's copy of the role → permission matrix.
 *
 * The API is the authority (`apps/api/src/nexus_api/core/operator_permissions.py`).
 * This test reads that file — not a hand-written snapshot — so the two copies
 * cannot drift apart without a red test (criterion 1.5). It also pins the
 * table Luis decided on 2026-11-25 (criterion 1.2).
 */
import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { PERMISSIONS, can, type Permission } from "../permissions";

const API_MATRIX = path.resolve(
  __dirname,
  "../../../../api/src/nexus_api/core/operator_permissions.py",
);

/** `OPERATOR_PERMISSIONS = { "read": ("admin", …), … }` → a plain object. */
function readApiMatrix(): Record<string, string[]> {
  const source = fs.readFileSync(API_MATRIX, "utf8");
  const block = source.match(/OPERATOR_PERMISSIONS[^=]*=\s*\{([\s\S]*?)\n\}/);
  if (!block?.[1]) throw new Error("OPERATOR_PERMISSIONS not found in operator_permissions.py");
  const matrix: Record<string, string[]> = {};
  for (const line of block[1].matchAll(/"([a-z_]+)"\s*:\s*\(([^)]*)\)/g)) {
    const [, permission, roles] = line;
    matrix[permission as string] = [...(roles as string).matchAll(/"([a-z_]+)"/g)].map((m) => m[1] as string);
  }
  return matrix;
}

const active = (role: string) => ({ role, access: "ok" });

describe("permission matrix (spec 079, requisito 1)", () => {
  it("matches the API's matrix exactly, in the same order", () => {
    const api = readApiMatrix();
    expect(Object.keys(api)).toEqual(Object.keys(PERMISSIONS));
    for (const [permission, roles] of Object.entries(PERMISSIONS)) {
      expect(api[permission]).toEqual([...roles]);
    }
  });

  it("admin has every permission", () => {
    for (const permission of Object.keys(PERMISSIONS) as Permission[]) {
      expect(can(active("admin"), permission)).toBe(true);
    }
  });

  it("qa_operator reads, tests and operates — nothing delicate, nothing platform-wide", () => {
    const granted = (Object.keys(PERMISSIONS) as Permission[]).filter((p) => can(active("qa_operator"), p));
    expect(granted).toEqual(["read", "qa", "operate"]);
  });

  it("viewer only reads", () => {
    const granted = (Object.keys(PERMISSIONS) as Permission[]).filter((p) => can(active("viewer"), p));
    expect(granted).toEqual(["read"]);
  });

  it("an unknown role has no permission at all (criterion 1.4)", () => {
    expect(can(active("owner"), "read")).toBe(false);
    expect(can(active(""), "read")).toBe(false);
  });

  it("a disabled account has no permission whatever its role (criterion 1.4)", () => {
    expect(can({ role: "admin", access: "disabled" }, "read")).toBe(false);
  });
});
