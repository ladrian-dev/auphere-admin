import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, relative } from "node:path";

/**
 * Shared by the three generators: write the file, or with `--check` fail when
 * the committed one differs (spec 031, D13–D16). CI runs the `--check` form, so
 * a token, a word or a route that changed upstream fails the build the same day.
 */
export function emit(path: string, content: string): void {
  const check = process.argv.includes("--check");
  const rel = relative(process.cwd(), path);
  if (check) {
    const current = existsSync(path) ? readFileSync(path, "utf8") : "";
    if (current !== content) {
      console.error(`${rel} is stale: run \`pnpm gen\` in apps/mobile`);
      process.exit(1);
    }
    return;
  }
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
  console.log(`wrote ${rel}`);
}

export const BANNER = "// GENERATED — do not edit. Source and generator named below; run `pnpm gen`.\n";
