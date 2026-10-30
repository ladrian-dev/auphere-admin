import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Spec 048 (requirement 3.8; T027): the pass to Reservas is automatic — it runs
 * in every deploy (`scripts/pass_booking_to_reservas.py`). The panel has no
 * screen, button, breadcrumb or call to pass a client by hand: no
 * `/tenants/legacy-booking`, no `GET /admin/reservas/legacy-booking`, no
 * `POST /admin/tenants/{id}/reservas/pass`.
 *
 * Sweeps the panel's code without the tests, which may name it to say it is gone.
 */
const SRC = join(import.meta.dirname, "..", "..");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return entry === "__tests__" || entry === "node_modules" ? [] : files(full);
    return /\.(ts|tsx)$/.test(entry) ? [full] : [];
  });
}

describe("spec 048 · no manual pass to Reservas in the panel", () => {
  it("no file of the panel offers it", () => {
    const offenders = files(SRC)
      .filter((file) => /legacy-booking|reservas\/pass|backend-reservas/.test(readFileSync(file, "utf8")))
      .map((file) => relative(SRC, file));
    expect(offenders).toEqual([]);
  });

  it("its page is gone", () => {
    const dir = join(SRC, "app", "(dashboard)", "tenants");
    expect(readdirSync(dir)).not.toContain("legacy-booking");
  });
});
