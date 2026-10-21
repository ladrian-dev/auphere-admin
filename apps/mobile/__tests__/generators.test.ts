import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { tokens } from "@/theme/tokens.gen";
import { liteMessages } from "@/i18n/lite.gen";

/**
 * Spec 031 (T012, R14.3, R14.6): what is shared with the console arrives
 * generated, and CI fails the day it drifts.
 */
const root = join(__dirname, "..");
const run = (script: string, ...args: string[]) =>
  execFileSync(process.execPath, [join(root, "scripts", script), ...args], { cwd: root, stdio: "pipe" });

describe("gen-tokens", () => {
  it("converts the console's OKLCH roles to the brand hex, in light and dark", () => {
    expect(tokens.light.primary).toBe("#2CC295");
    expect(tokens.light.primaryText).toBe("#03624C");
    expect(tokens.light.background).toBe("#F1F7F6");
    // Dark: the primary stays the brand green; the ground is the warm ink, not green.
    expect(tokens.dark.primary).toBe("#2CC295");
    expect(tokens.dark.background).not.toBe(tokens.light.background);
    expect(tokens.dark.foreground).toBe(tokens.light.background);
  });

  it("keeps the motion budget under 300 ms", () => {
    for (const ms of Object.values(tokens.duration)) expect(ms).toBeLessThanOrEqual(300);
  });
});

describe("gen-i18n", () => {
  it("brings the console's words for «Tomar el control» and «Necesita humano», in ES and EN", () => {
    expect(liteMessages["inbox.composer.takeover"]).toEqual({ es: "Tomar el control", en: "Take over" });
    expect(liteMessages["inbox.badge.waiting"]).toEqual({ es: "Necesita humano", en: "Needs a human" });
  });

  it("the attention button names what it does, in both languages (spec 042, T041, R9.3)", () => {
    expect(liteMessages["lite.attention.attend"]).toEqual({ es: "Atender ahora", en: "Answer now" });
  });
});

describe("--check", () => {
  it.each(["gen-schema.mts", "gen-tokens.mts", "gen-i18n.mts"])("%s passes on the committed file", (script) => {
    expect(() => run(script, "--check")).not.toThrow();
  });

  it("fails when the committed file differs from what the source gives", () => {
    const file = join(root, "src/theme/tokens.gen.ts");
    const committed = readFileSync(file, "utf8");
    try {
      writeFileSync(file, committed.replace("#2CC295", "#2CC296"));
      expect(() => run("gen-tokens.mts", "--check")).toThrow();
    } finally {
      writeFileSync(file, committed);
    }
  });
});
