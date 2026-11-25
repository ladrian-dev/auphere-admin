/**
 * Spec 078, requisito 5: el token de servicio del panel sale de un solo
 * sitio, y en producción el panel no habla con la API con el valor de
 * desarrollo ni sin token. La API ya se niega a arrancar así en producción;
 * esto hace que el panel falle con un mensaje claro en vez de con 401s.
 */
import fs from "node:fs";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { adminToken } = await import("../admin-token");

afterEach(() => vi.unstubAllEnvs());

describe("adminToken (spec 078, requisito 5)", () => {
  it("devuelve el token configurado", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXUS_ADMIN_TOKEN", "a-real-service-token");
    expect(adminToken()).toBe("a-real-service-token");
  });

  it("en producción, sin token, falla con un mensaje que dice qué falta", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXUS_ADMIN_TOKEN", undefined);
    expect(() => adminToken()).toThrow(/NEXUS_ADMIN_TOKEN/);
  });

  it("en producción, con el valor de desarrollo, falla", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXUS_ADMIN_TOKEN", "dev-admin-token-change-me");
    expect(() => adminToken()).toThrow(/NEXUS_ADMIN_TOKEN/);
  });

  it("en desarrollo, sin token, usa el de desarrollo", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXUS_ADMIN_TOKEN", undefined);
    expect(adminToken()).toBe("dev-admin-token-change-me");
  });

  it("nadie más lee NEXUS_ADMIN_TOKEN ni repite el valor de desarrollo", () => {
    const src = path.resolve(__dirname, "../..");
    const offenders: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== "__tests__" && entry.name !== "node_modules") walk(full);
          continue;
        }
        if (!/\.[cm]?[jt]sx?$/.test(entry.name) || full.endsWith(path.join("lib", "admin-token.ts"))) continue;
        const text = fs.readFileSync(full, "utf8");
        if (/process\.env\.NEXUS_ADMIN_TOKEN|dev-admin-token-change-me/.test(text)) {
          offenders.push(path.relative(src, full));
        }
      }
    };
    walk(src);
    expect(offenders).toEqual([]);
  });
});
