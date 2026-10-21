import { Easing, FadeIn, FadeInDown, FadeOut, LinearTransition, ReduceMotion } from "react-native-reanimated";

import { useSystemAppearance } from "@/theme/system-appearance";

import { durations } from "./durations";

/**
 * Spec 031, D24 and R14.7; spec 042, R2.5, R2.6, R4.5: the app's few
 * entrances, in one place. With «Reducir movimiento» on, every one of them
 * becomes a plain fade (or nothing): no slide, no layout morph. The app
 * decides what reduced motion looks like, so Reanimated is told `Never`
 * explicitly: `System` would read the setting only at launch, and `Always`
 * would skip the fade that *is* the reduced-motion alternative.
 */
export type Motion = ReturnType<typeof motionFor>;

export function motionFor(reduced: boolean) {
  const fade = FadeIn.duration(durations.fast).reduceMotion(ReduceMotion.Never);
  return {
    reduced,
    /** A row, a bubble or a card arriving. */
    enter: reduced ? fade : FadeInDown.duration(durations.enter).reduceMotion(ReduceMotion.Never),
    exit: FadeOut.duration(durations.exit).reduceMotion(ReduceMotion.Never),
    /** Siblings moving to make room, and a surface changing height (R2.5): none when reduced. */
    layout: reduced
      ? undefined
      : LinearTransition.duration(durations.state).easing(Easing.out(Easing.cubic)).reduceMotion(ReduceMotion.Never),
    fade,
  };
}

/** Follows the phone's setting live (R4.5), not the value at launch. */
export function useMotion(): Motion {
  return motionFor(useSystemAppearance().reduceMotion);
}
