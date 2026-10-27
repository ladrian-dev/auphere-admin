import { describe, expect, it } from "vitest";

import { NAV_COOKIE, resolveConsoleVersion } from "../console-version";

/** Spec 047 (R55.2): solo `"v2"` abre la consola nueva; todo lo demás es la de hoy. */
describe("resolveConsoleVersion", () => {
  it.each([
    [{ console_version: "v2" as const }, "v2"],
    [{ console_version: "v1" as const }, "v1"],
    [{}, "v1"],
    [null, "v1"],
    [undefined, "v1"],
    // Un valor que esta consola no conoce no abre nada nuevo.
    [{ console_version: "v3" as unknown as "v2" }, "v1"],
  ])("%j → %s", (me, expected) => {
    expect(resolveConsoleVersion(me)).toBe(expected);
  });

  it("el menú plegado se recuerda en su cookie", () => {
    expect(NAV_COOKIE).toBe("nexus-console.nav");
  });
});
