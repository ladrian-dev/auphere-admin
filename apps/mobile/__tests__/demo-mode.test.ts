import { demoOf } from "@/config";

/**
 * Spec 069, Requisito 23: the example business exists only in a development
 * build that asks for it. The store profiles never ask (version.test.ts).
 */
describe("the example business (R23.1, R23.2)", () => {
  it("is on only in a development build started with EXPO_PUBLIC_DEMO=1", () => {
    expect(demoOf("1", true)).toBe(true);
  });

  it("is off outside __DEV__, whatever the environment says", () => {
    expect(demoOf("1", false)).toBe(false);
  });

  it("is off when not asked for, or asked for with anything but 1", () => {
    for (const v of [undefined, "", "0", "true", "yes"]) expect(demoOf(v, true)).toBe(false);
  });
});
