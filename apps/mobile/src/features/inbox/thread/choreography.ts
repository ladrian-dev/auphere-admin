import { Easing, FadeIn, FadeInDown, FadeOut, FadeOutDown, ReduceMotion } from "react-native-reanimated";

import { MICRO } from "@/motion/micro";

/**
 * «Tomar el control», the app's one choreography (spec 069, R2.3; design
 * §4.10): the agent's strip folds away in 120 ms, a 40 ms pause, and the box
 * rises in 240 ms. Nothing bounces and no step passes the 300 ms budget
 * (R2.4). With «Reducir movimiento» there is no fold: both happen at once, as
 * fades (R2.5).
 */
export const TAKE_OVER = { fold: 120, pause: 40, rise: 240 } as const;

/** When the box has risen: the cursor lands then, not under a moving surface. */
export const TAKE_OVER_SETTLED_MS = TAKE_OVER.fold + TAKE_OVER.pause + TAKE_OVER.rise;

/** The design's `cubic-bezier(.2,.9,.25,1)`, resolved when used (the Jest double of Reanimated has no `bezier`). */
function rise() {
  return typeof Easing.bezier === "function" ? Easing.bezier(0.2, 0.9, 0.25, 1) : Easing.out(Easing.cubic);
}

export function takeOverMotion(reduced: boolean) {
  if (reduced) {
    return {
      fold: FadeOut.duration(MICRO.fade).reduceMotion(ReduceMotion.Never),
      rise: FadeIn.duration(MICRO.fade).reduceMotion(ReduceMotion.Never),
    };
  }
  return {
    fold: FadeOutDown.duration(TAKE_OVER.fold).easing(Easing.in(Easing.quad)).reduceMotion(ReduceMotion.Never),
    rise: FadeInDown.delay(TAKE_OVER.fold + TAKE_OVER.pause)
      .duration(TAKE_OVER.rise)
      .easing(rise())
      .withInitialValues({ opacity: 0, transform: [{ translateY: 22 }] })
      .reduceMotion(ReduceMotion.Never),
  };
}
