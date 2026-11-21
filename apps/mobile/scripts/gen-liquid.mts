import { readFileSync } from "node:fs";
import { join } from "node:path";

import ts from "typescript";

import { BANNER, emit } from "./_write.mts";

/**
 * Spec 069, D8 (R5.1–R5.3): the living liquid of «Entrar» is the console's
 * (spec 066, requirement 2), not a copy. One model and one shader for the web
 * and the phone; if the console changes either, `--check` fails the same day.
 *
 * - **The model** (`liquid-backdrop-model.ts`: the invisible finger, the
 *   waves, `step()`, `touch()`) is dependency-free TypeScript and every
 *   top-level statement is copied verbatim, comments included. A file-level
 *   `"worklet"` directive goes on top so every function in it can run on the
 *   UI thread, inside Reanimated's frame callback. A worklet captures what it
 *   uses **when it is defined**, so the statements go in dependency order
 *   (`workletOrder`): on the web `touch()` may call `clamp01()`, declared
 *   below it, thanks to hoisting; as a worklet it would capture `undefined`.
 * - **The shader** (`FS` in `liquid-backdrop.tsx`, WebGL 1) is translated to
 *   Skia's SkSL by the fixed rules in `toSkSL()`, and nothing else. SkSL takes
 *   `vec2`, `vec3`, `mat2` as they are; what changes is the entry point, the
 *   uniforms, the output and the y axis (Skia's points down, the model's up).
 *   Two rules remove undefined behaviour without changing a pixel where the
 *   GLSL is defined: `smoothstep` with its edges reversed, and `pow` of a
 *   value that can be negative.
 */
const root = join(import.meta.dirname, "..");
const AUTH = "apps/console/src/components/auth";
const modelPath = join(root, "../console/src/components/auth/liquid-backdrop-model.ts");
const backdropPath = join(root, "../console/src/components/auth/liquid-backdrop.tsx");
const outPath = join(root, "src/features/entry/liquid.gen.ts");

/** The `FS` template literal of the console's backdrop. Fails loudly if it moved or grew an interpolation. */
export function extractFragmentShader(tsx: string): string {
  const m = /const FS = `([^`]*)`;/.exec(tsx);
  if (!m) throw new Error(`${AUTH}/liquid-backdrop.tsx: no \`const FS = \`…\`;\` to translate`);
  const fs = m[1]!;
  if (fs.includes("${")) throw new Error(`${AUTH}/liquid-backdrop.tsx: FS has an interpolation; the generator only copies plain text`);
  return fs;
}

const NUMBER = /^-?(?:\d+\.?\d*|\.\d+)$/;

/**
 * Rewrites every call to `name(...)`, innermost first. `rewrite` gets the
 * arguments as written (already rewritten themselves) and returns the new text,
 * or `null` to leave that call alone.
 */
function rewriteCalls(src: string, name: string, rewrite: (args: string[]) => string | null): string {
  const head = new RegExp(`(?<![\\w.])${name}\\(`, "g");
  let out = "";
  let from = 0;
  for (let m = head.exec(src); m; m = head.exec(src)) {
    if (m.index < from) continue;
    const open = m.index + m[0].length;
    const args: string[] = [];
    let depth = 0;
    let start = open;
    let i = open;
    for (; i < src.length; i++) {
      const c = src[i];
      if (c === "(") depth += 1;
      else if (c === ")") {
        if (depth === 0) break;
        depth -= 1;
      } else if (c === "," && depth === 0) {
        args.push(src.slice(start, i));
        start = i + 1;
      }
    }
    if (i >= src.length) throw new Error(`FS: unbalanced ${name}( at ${m.index}`);
    args.push(src.slice(start, i));
    const inner = args.map((a) => rewriteCalls(a, name, rewrite));
    const replaced = rewrite(inner);
    out += src.slice(from, m.index) + (replaced ?? `${name}(${inner.join(",")})`);
    from = i + 1;
    head.lastIndex = from;
  }
  return out + src.slice(from);
}

/**
 * GLSL ES 1.0 (WebGL 1) → SkSL, by fixed rules. Anything the rules do not
 * cover makes the generator throw instead of emitting a shader that might not
 * compile on the phone.
 */
export function toSkSL(glsl: string): string {
  let s = glsl;
  // SkSL has no default-precision statements: `float` is full precision.
  s = s.replace(/^[ \t]*precision\s+\w+\s+float\s*;[ \t]*\n?/m, "");
  // `uniform vec2 R; … uniform vec4 W[4];` → `uniform float2 R; … uniform float4 W[4];`
  s = s.replace(/\buniform\s+vec([234])\b/g, "uniform float$1");
  // The entry point: a colour returned for a coordinate, not written to a global.
  s = s.replace(/\bvoid\s+main\s*\(\s*\)\s*\{/, "half4 main(float2 fragCoord){");
  // Skia's coordinate grows downwards; the model and the shader's vignettes read y upwards.
  s = s.replace(/\bgl_FragCoord\.xy\b/g, "float2(fragCoord.x, R.y - fragCoord.y)");
  s = s.replace(/\bgl_FragColor\s*=\s*vec4\(([^;]*)\)\s*;/g, "return half4($1);");
  // smoothstep(a, b, x) with a > b is undefined in GLSL and in Metal; with the formula every
  // driver uses it is exactly 1 - smoothstep(b, a, x), which is defined everywhere.
  s = rewriteCalls(s, "smoothstep", (args) => {
    if (args.length !== 3) return null;
    const [a, b, x] = args.map((v) => v.trim()) as [string, string, string];
    if (!NUMBER.test(a) || !NUMBER.test(b) || Number(a) <= Number(b)) return null;
    return `(1.-smoothstep(${b},${a},${x}))`;
  });
  // pow(x, 2.) is undefined for x < 0 (GLSL, Metal fast math); a square is the same number and always defined.
  s = rewriteCalls(s, "pow", (args) => {
    if (args.length !== 2 || Number(args[1]!.trim()) !== 2) return null;
    const x = args[0]!.trim();
    return `((${x})*(${x}))`;
  });
  for (const [left, why] of [
    [/\bgl_\w+/, "a gl_ built-in"],
    [/\bprecision\b/, "a precision statement"],
    [/\bvoid\s+main\b/, "the GLSL entry point"],
    [/\buniform\s+vec\d/, "a GLSL uniform type"],
    [/\b(?:texture2D|varying|attribute|discard)\b/, "a WebGL-only construct"],
  ] as const) {
    if (left.test(s)) throw new Error(`FS → SkSL: ${why} is left after the rules; add a rule to scripts/gen-liquid.mts`);
  }
  if (!s.includes("half4 main(float2 fragCoord)")) throw new Error("FS → SkSL: no entry point after the rules");
  return s;
}

/** What a top-level statement declares (functions, constants, types). */
function declared(st: ts.Statement): string[] {
  if ((ts.isFunctionDeclaration(st) || ts.isTypeAliasDeclaration(st) || ts.isInterfaceDeclaration(st)) && st.name) return [st.name.text];
  if (ts.isVariableStatement(st)) return st.declarationList.declarations.flatMap((d) => (ts.isIdentifier(d.name) ? [d.name.text] : []));
  return [];
}

/** Every identifier a statement mentions in code (comments are not nodes, so they never count). */
function mentioned(node: ts.Node, out = new Set<string>()): Set<string> {
  if (ts.isIdentifier(node)) out.add(node.text);
  ts.forEachChild(node, (child) => void mentioned(child, out));
  return out;
}

/**
 * The model's top-level statements, each verbatim with its own comments, in
 * an order where nothing is used before it is defined: a stable topological
 * sort, so a model that is already in order comes out as it is.
 */
export function workletOrder(source: string): string[] {
  const file = ts.createSourceFile("liquid-backdrop-model.ts", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const chunks = file.statements.map((st) => ({ text: source.slice(st.getFullStart(), st.getEnd()).trim(), names: declared(st), uses: mentioned(st) }));
  const owner = new Map<string, number>();
  chunks.forEach((c, i) => c.names.forEach((n) => owner.set(n, i)));
  const deps = chunks.map((c, i) => new Set([...c.uses].map((n) => owner.get(n)).filter((j): j is number => j !== undefined && j !== i)));
  const done = new Set<number>();
  const out: string[] = [];
  while (out.length < chunks.length) {
    const next = chunks.findIndex((_, i) => !done.has(i) && [...deps[i]!].every((j) => done.has(j)));
    if (next < 0) throw new Error(`${AUTH}/liquid-backdrop-model.ts: a cycle between top-level declarations; worklets cannot capture it`);
    done.add(next);
    out.push(chunks[next]!.text);
  }
  return out;
}

const model = workletOrder(readFileSync(modelPath, "utf8")).join("\n\n");
const sksl = toSkSL(extractFragmentShader(readFileSync(backdropPath, "utf8")));

emit(
  outPath,
  `${BANNER}// Source: ${AUTH}/liquid-backdrop-model.ts (each statement verbatim, in dependency order) and the FS of ${AUTH}/liquid-backdrop.tsx (as SkSL) · generator: scripts/gen-liquid.mts\n` +
    `// The directive below makes every function in this file a worklet (Reanimated's UI thread); a worklet captures\n` +
    `// what it uses when it is defined, hence the order.\n` +
    `"worklet";\n\n` +
    model.trimEnd() +
    "\n\n" +
    "/**\n" +
    " * The console's fragment shader, as Skia SkSL (scripts/gen-liquid.mts, `toSkSL`):\n" +
    " * `half4 main(float2 fragCoord)`, `float2/3/4` uniforms and the y axis flipped,\n" +
    " * so `R`, `T`, `P` and `W[4]` mean what they mean on the web.\n" +
    " */\n" +
    `export const LIQUID_SKSL = \`${sksl}\`;\n`,
);
