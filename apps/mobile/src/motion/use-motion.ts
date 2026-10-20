import {
  FadeIn,
  FadeInDown,
  FadeOut,
  LinearTransition,
  ReduceMotion,
  useReducedMotion,
} from "react-native-reanimated";

import { durations } from "./durations";

/**
 * Spec 031, D24 and R14.7: the app's few entrances, in one place. With
 * «Reduce motion» on, every one of them becomes a plain fade (or nothing):
 * no slide, no layout morph. Reanimated also honours the system setting by
 * itself (`ReduceMotion.System`); this makes the choice explicit and testable.
 */
export type Motion = ReturnType<typeof motionFor>;

export function motionFor(reduced: boolean) {
  const fade = FadeIn.duration(durations.fast).reduceMotion(ReduceMotion.System);
  return {
    reduced,
    /** A row, a bubble or a card arriving. */
    enter: reduced ? fade : FadeInDown.duration(durations.enter).reduceMotion(ReduceMotion.System),
    exit: FadeOut.duration(durations.exit).reduceMotion(ReduceMotion.System),
    /** Siblings moving to make room: none when reduced. */
    layout: reduced ? undefined : LinearTransition.duration(durations.state).reduceMotion(ReduceMotion.System),
    fade,
  };
}

export function useMotion(): Motion {
  return motionFor(useReducedMotion());
}
