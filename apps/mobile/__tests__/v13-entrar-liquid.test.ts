import { execFileSync } from "node:child_process";
import { readFileSync, realpathSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import ts from "typescript";

import { APP_SLOW_FRAME_MS, WARMUP_FRAMES, framePace, liquidUniforms, stillUniforms } from "@/features/entry/liquid-pace";
import { LIQUID_SKSL, MAX_WAVES, SLOW_FRAMES_TO_STILL, SLOW_FRAME_MS, STILL_T, addWave, initialState, step, touch } from "@/features/entry/liquid.gen";

/**
 * Spec 069 (D8, R5.1–R5.3, R22.4): the liquid of «Entrar» is the console's
 * (spec 066, requirement 2) — the same model and the same shader, generated,
 * and checked the day the console changes it.
 */
const root = join(__dirname, "..");
const consoleAuth = join(root, "../console/src/components/auth");
const generated = join(root, "src/features/entry/liquid.gen.ts");
const run = (...args: string[]) => execFileSync(process.execPath, [join(root, "scripts/gen-liquid.mts"), ...args], { cwd: root, stdio: "pipe" });

describe("gen-liquid", () => {
  it("passes --check on the committed file, and fails when it drifts from the console", () => {
    expect(() => run("--check")).not.toThrow();
    const committed = readFileSync(generated, "utf8");
    try {
      writeFileSync(generated, committed.replace("IDLE_AFTER_S = 2.5", "IDLE_AFTER_S = 3"));
      expect(() => run("--check")).toThrow();
    } finally {
      writeFileSync(generated, committed);
    }
  });

  it("copies every statement of the console's model verbatim, as worklets for the UI thread", () => {
    const source = readFileSync(join(consoleAuth, "liquid-backdrop-model.ts"), "utf8");
    const file = ts.createSourceFile("model.ts", source, ts.ScriptTarget.Latest, true);
    const out = readFileSync(generated, "utf8");
    expect(file.statements.length).toBeGreaterThan(10);
    for (const st of file.statements) expect(out).toContain(source.slice(st.getFullStart(), st.getEnd()).trim());
    // A file-level directive, before any statement: every function in the file runs in the frame callback.
    expect(out.split("\n").find((l) => !l.startsWith("//") && l.trim() !== "")).toBe('"worklet";');
    // A worklet captures what it uses when it is defined: nothing may be used above its definition.
    expect(out.indexOf("export function clamp01")).toBeLessThan(out.indexOf("export function touch"));
  });

  it("the model works as the console's: a touch takes the pointer there, clamped", () => {
    const s = initialState();
    touch(s, 1.4, -0.2, 3);
    expect([s.ptr.tx, s.ptr.ty, s.ptr.te, s.ptr.touched]).toEqual([1, 0, 1, 3]);
    step(s, 3.1, 0.05);
    expect(s.ptr.x).toBeGreaterThan(0.72);
    expect(s.ptr.y).toBeLessThan(0.62);
  });

  it("translates the console's fragment shader to SkSL by its fixed rules", () => {
    expect(LIQUID_SKSL).toContain("uniform float2 R;uniform float T;uniform float3 P;uniform float4 W[4];");
    expect(LIQUID_SKSL).toContain("half4 main(float2 fragCoord){");
    // Skia's y grows downwards; the model's grows upwards.
    expect(LIQUID_SKSL).toContain("float2(fragCoord.x, R.y - fragCoord.y)/R");
    expect(LIQUID_SKSL).toContain("return half4(col,1.);");
    // Undefined behaviour gone, same numbers: the reversed smoothstep and pow of a negative.
    expect(LIQUID_SKSL).toContain("(1.-smoothstep(.04,.5,uv.y))*.78");
    expect(LIQUID_SKSL).toContain("exp(-(((rl-age*.5)*11.)*((rl-age*.5)*11.)))");
    expect(LIQUID_SKSL).not.toMatch(/gl_|precision|void main|uniform vec|smoothstep\(\.5,\.04/);
    // Nothing else of the shader changes (R22.4: no extra passes, the same cost).
    const fs = /const FS = `([^`]*)`;/.exec(readFileSync(join(consoleAuth, "liquid-backdrop.tsx"), "utf8"))![1]!;
    for (const line of ["float fbm(vec2 p){float v=0.,a=.5;mat2 m=mat2(1.4,1.1,-1.1,1.4);", "float f=fbm(b+3.4*r);", "col+=c4*(inf*.28+rip*.42)+c2*inf*.28;"]) {
      expect(fs).toContain(line);
      expect(LIQUID_SKSL).toContain(line);
    }
  });
});

describe("Skia compiles and draws it", () => {
  // CanvasKit is Skia's own build in WebAssembly (a dependency of react-native-skia): the same SkSL compiler.
  type CK = {
    RuntimeEffect: { Make: (sksl: string, onError?: (e: string) => void) => Effect | null };
    MakeSurface: (w: number, h: number) => { getCanvas: () => Canvas } | null;
    Paint: new () => { setShader: (s: unknown) => void };
    ColorType: { RGBA_8888: unknown };
    AlphaType: { Unpremul: unknown };
    ColorSpace: { SRGB: unknown };
  };
  type Effect = { getUniformCount: () => number; getUniformName: (i: number) => string; getUniformFloatCount: () => number; makeShader: (u: number[]) => unknown };
  type Canvas = { drawPaint: (p: unknown) => void; readPixels: (x: number, y: number, info: object) => Uint8Array };
  let CanvasKit: CK;

  beforeAll(async () => {
    const skia = realpathSync(join(root, "node_modules/@shopify/react-native-skia"));
    const bin = join(skia, "../../canvaskit-wasm/bin/full");
    const init = require(join(bin, "canvaskit.js")) as (o: { wasmBinary: Uint8Array }) => Promise<CK>;
    CanvasKit = await init({ wasmBinary: new Uint8Array(readFileSync(join(bin, "canvaskit.wasm"))) });
  }, 30_000);

  it("is a valid runtime effect with the four uniforms the model drives", () => {
    const errors: string[] = [];
    const effect = CanvasKit.RuntimeEffect.Make(LIQUID_SKSL, (e) => errors.push(e));
    expect(errors).toEqual([]);
    expect(effect).not.toBeNull();
    const names = Array.from({ length: effect!.getUniformCount() }, (_, i) => effect!.getUniformName(i));
    expect(names).toEqual(["R", "T", "P", "W"]);
    expect(effect!.getUniformFloatCount()).toBe(2 + 1 + 3 + MAX_WAVES * 4);
  });

  it("the still frame is opaque, with the dark vignette at the bottom where the headline sits", () => {
    const effect = CanvasKit.RuntimeEffect.Make(LIQUID_SKSL)!;
    const [w, h] = [60, 120];
    const u = stillUniforms(w, h, initialState());
    const flat = [...u.R, u.T, ...u.P, ...u.W];
    const surface = CanvasKit.MakeSurface(w, h)!;
    const paint = new CanvasKit.Paint();
    paint.setShader(effect.makeShader(flat));
    surface.getCanvas().drawPaint(paint);
    const px = surface.getCanvas().readPixels(0, 0, {
      width: w,
      height: h,
      colorType: CanvasKit.ColorType.RGBA_8888,
      alphaType: CanvasKit.AlphaType.Unpremul,
      colorSpace: CanvasKit.ColorSpace.SRGB,
    });
    const band = (y0: number, y1: number) => {
      let sum = 0;
      for (let y = y0; y < y1; y++) for (let x = 0; x < w; x++) sum += px[(y * w + x) * 4 + 1]!;
      return sum / ((y1 - y0) * w);
    };
    for (let i = 3; i < px.length; i += 4) expect(px[i]).toBe(255);
    expect(band(h - 10, h)).toBeLessThan(band(h / 2 - 10, h / 2 + 10));
  });
});

describe("the frame budget (R22.4)", () => {
  it("is the app's own, under 50 fps, not the web's", () => {
    expect(APP_SLOW_FRAME_MS).toBe(20);
    expect(SLOW_FRAME_MS).toBe(50); // the console's model stays as it is
  });

  it("freezes after 30 slow frames in a row, and only then", () => {
    let pace = { slow: 0, freeze: false };
    for (let i = 0; i < SLOW_FRAMES_TO_STILL - 1; i++) pace = framePace(pace.slow, 33);
    expect(pace).toEqual({ slow: SLOW_FRAMES_TO_STILL - 1, freeze: false });
    expect(framePace(pace.slow, 33).freeze).toBe(true);
  });

  it("a frame on time starts the count again; one exactly at the budget is on time", () => {
    expect(framePace(12, 16.7)).toEqual({ slow: 0, freeze: false });
    expect(framePace(29, APP_SLOW_FRAME_MS)).toEqual({ slow: 0, freeze: false });
    expect(framePace(3, APP_SLOW_FRAME_MS + 0.1)).toEqual({ slow: 4, freeze: false });
  });

  it("the first frame, which has no previous one, counts as neither", () => {
    expect(framePace(5, null)).toEqual({ slow: 5, freeze: false });
  });

  it("the frames right after it starts (launch, a transition, the keyboard) do not count", () => {
    let pace = { slow: 0, freeze: false };
    for (let i = 0; i < WARMUP_FRAMES; i++) pace = framePace(pace.slow, 80, i);
    expect(pace).toEqual({ slow: 0, freeze: false });
    for (let i = WARMUP_FRAMES; i < WARMUP_FRAMES + SLOW_FRAMES_TO_STILL; i++) pace = framePace(pace.slow, 80, i);
    expect(pace.freeze).toBe(true);
  });
});

describe("what the shader is fed", () => {
  it("the still frame is the console's: T at STILL_T, a quiet pointer, no waves", () => {
    const s = initialState();
    addWave(s, 0.5, 0.5, 1, 1);
    const u = stillUniforms(390, 420, s);
    expect(u.R).toEqual([390, 420]);
    expect(u.T).toBe(STILL_T);
    expect(u.P).toEqual([s.ptr.x, s.ptr.y, 0.35]);
    expect(u.W).toEqual(Array(16).fill(-99));
  });

  it("a live frame carries the clock, the pointer's energy and the waves", () => {
    const s = initialState();
    touch(s, 0.2, 0.8, 1);
    addWave(s, 0.2, 0.8, 1, 1);
    step(s, 1.1, 0.1);
    const u = liquidUniforms(390, 420, 1.1, s);
    expect(u.T).toBe(1.1);
    expect(u.P[2]).toBeGreaterThan(0);
    // The shader reads 32-bit floats: compare at that precision.
    expect(u.W.slice(0, 4).map((v) => Number(v.toFixed(5)))).toEqual([0.2, 0.8, 1, 1]);
    expect(u.W.slice(4, 8)).toEqual([0, 0, -99, 0]);
  });
});
