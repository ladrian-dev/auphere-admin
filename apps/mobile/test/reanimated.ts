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
  };
  return b;
}

export const Easing = { out: (f: unknown) => f, inOut: (f: unknown) => f, cubic: () => 0, quad: () => 0 };

export const FadeIn = builder("FadeIn");
export const FadeInDown = builder("FadeInDown");
export const FadeOut = builder("FadeOut");
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
export const withRepeat = jest.fn((v: unknown) => v);
export const withTiming = jest.fn((v: unknown) => v);
export const cancelAnimation = jest.fn();

const Animated = { View, createAnimatedComponent: <C,>(c: C) => c };
export default Animated;
