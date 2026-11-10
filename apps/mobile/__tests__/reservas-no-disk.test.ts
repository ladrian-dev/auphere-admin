import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * Spec 044, plan «Aislamiento» (constitution §I) and spec 031: nothing about a
 * business's customers is written on the phone. Reservas carries names and
 * phone numbers of the business's own customers; they live in React Query's
 * memory and nowhere else. This sweeps every file of Reservas — the adapter,
 * the example source, the hooks, the screens — for a way to disk.
 */
const ROOT = join(__dirname, "..", "src");
const STORAGE = /from\s+["'](expo-secure-store|expo-file-system[^"']*|@react-native-async-storage\/async-storage|expo-sqlite|react-native-mmkv)["']|persistQueryClient|createAsyncStoragePersister/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

const RESERVAS = [
  join(ROOT, "api", "reservas.ts"),
  join(ROOT, "api", "reservas-demo.ts"),
  join(ROOT, "api", "reservas-hooks.ts"),
  join(ROOT, "lib", "reservas-model.ts"),
  ...files(join(ROOT, "features", "reservas")),
  ...files(join(ROOT, "app", "(app)", "reservas")),
  ...files(join(ROOT, "app", "reserva")),
];

describe("Reservas never goes to disk (§I, 031)", () => {
  it.each(RESERVAS.map((f) => [f.slice(ROOT.length + 1), f]))("%s has no way to storage", (_name, file) => {
    expect(readFileSync(file, "utf8")).not.toMatch(STORAGE);
  });

  it("and the query client has no persister anywhere in the app", () => {
    for (const f of files(ROOT)) expect(readFileSync(f, "utf8")).not.toMatch(/persistQueryClient|createAsyncStoragePersister/);
  });
});
