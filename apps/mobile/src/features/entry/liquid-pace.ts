import { SLOW_FRAMES_TO_STILL, STILL_T, wavesUniform, type LiquidState } from "./liquid.gen";

/**
 * When the liquid gives up (spec 069, R5.2, R22.4): the app's own budget, not
 * the web's. The console's model freezes after frames over 50 ms; on the phone
 * the liquid must hold 50 fps or stand still, so a frame over 20 ms is slow.
 * The console's constants stay untouched in `liquid.gen.ts`; only the count of
 * frames in a row (`SLOW_FRAMES_TO_STILL`, 30) is shared.
 */
export const APP_SLOW_FRAME_MS = 20;

/**
 * The frames right after the liquid starts running do not count: a cold
 * start, the screen's transition or the keyboard can stall the first second
 * of any phone, and a freeze is for good (until the screen is mounted again).
 */
export const WARMUP_FRAMES = 30;

export type Pace = { slow: number; freeze: boolean };

/**
 * One frame's verdict. `frameMs` is the time since the previous frame (what
 * the phone actually shows, so «below 50 fps» is literal); `null` on the first
 * frame, which has no previous one and changes nothing. `frame` is the
 * frame's index since the liquid started running; within `WARMUP_FRAMES`
 * nothing counts. A frame on time starts the count again: only a sustained
 * slowdown freezes, never one hiccup.
 */
export function framePace(slow: number, frameMs: number | null, frame: number = WARMUP_FRAMES): Pace {
  "worklet";
  if (frameMs === null || frame < WARMUP_FRAMES) return { slow, freeze: false };
  const next = frameMs > APP_SLOW_FRAME_MS ? slow + 1 : 0;
  return { slow: next, freeze: next >= SLOW_FRAMES_TO_STILL };
}

/** The shader's uniforms, by name, as Skia's `<Shader uniforms>` reads them. */
export type LiquidUniforms = { R: [number, number]; T: number; P: [number, number, number]; W: number[] };

/** A live frame: the clock, the pointer with its energy, and the four waves (empty slots never paint). */
export function liquidUniforms(w: number, h: number, t: number, s: LiquidState): LiquidUniforms {
  "worklet";
  return { R: [w, h], T: t, P: [s.ptr.x, s.ptr.y, s.ptr.e], W: Array.from(wavesUniform(s)) };
}

/** The still frame (R5.2; console R2.6): one of the instants that reads best, a quiet pointer, no waves. */
export function stillUniforms(w: number, h: number, s: LiquidState): LiquidUniforms {
  "worklet";
  return { R: [w, h], T: STILL_T, P: [s.ptr.x, s.ptr.y, 0.35], W: Array(16).fill(-99) as number[] };
}
