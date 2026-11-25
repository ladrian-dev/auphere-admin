/**
 * A minimal Reanimated for Jest: only what the app uses. Entrances are inert
 * builders (chainable, recordable), animated views are plain views, and the
 * hooks behave like their static values. `useReducedMotion` is a jest.fn so a
 * test can turn «Reduce motion» on.
 */
import { View } from "react-native";

type Builder = {
  name: string;
  duration: (ms: number) => Builder;
  easing: (e: unknown) => Builder;
  reduceMotion: (m: unknown) => Builder;
  withInitialValues: (v: unknown) => Builder;
  delay: (ms: number) => Builder;
  ms?: number;
  /** What the app told Reanimated about «Reduce motion» (spec 042, T022). */
  motion?: unknown;
};

function builder(name: string, extra: Partial<Builder> = {}): Builder {
  const b: Builder = {
    name,
    ...extra,
    duration(ms) {
      return builder(name, { ...extra, ms });
    },
    easing() {
      return builder(name, extra);
    },
    reduceMotion(m) {
      return builder(name, { ...extra, motion: m });
    },
    withInitialValues() {
      return builder(name, extra);
    },
    delay() {
      return builder(name, extra);
    },
  };
  return b;
}

export const Easing = {
  out: (f: unknown) => f,
  in: (f: unknown) => f,
  inOut: (f: unknown) => f,
  cubic: () => 0,
  quad: () => 0,
  linear: () => 0,
  bezier: () => () => 0,
};

export const FadeIn = builder("FadeIn");
export const FadeInDown = builder("FadeInDown");
export const FadeOut = builder("FadeOut");
export const FadeInUp = builder("FadeInUp");
export const FadeOutDown = builder("FadeOutDown");
export const LinearTransition = builder("LinearTransition");
export const ReduceMotion = { System: "system", Always: "always", Never: "never" };

export const useReducedMotion = jest.fn(() => false);
export const useSharedValue = <T,>(v: T) => {
  const sv = {
    value: v,
    get: () => sv.value,
    set: (next: T | ((cur: T) => T)) => {
      sv.value = typeof next === "function" ? (next as (cur: T) => T)(sv.value) : next;
    },
  };
  return sv;
};
export const useAnimatedStyle = (fn: () => object) => fn();
/** Spec 069: animated SVG props (the drawn checks) resolve to their static values. */
export const useAnimatedProps = (fn: () => object) => fn();
export const withRepeat = jest.fn((v: unknown) => v);
export const withTiming = jest.fn((v: unknown) => v);
export const withDelay = jest.fn((_ms: number, v: unknown) => v);
export const withSequence = jest.fn((...vs: unknown[]) => vs[vs.length - 1]);
export const withSpring = jest.fn((v: unknown) => v);
export const runOnJS = <F,>(f: F) => f;
export const cancelAnimation = jest.fn();

const Animated = { View, createAnimatedComponent: <C,>(c: C) => c };
export default Animated;
