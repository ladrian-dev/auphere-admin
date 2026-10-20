/**
 * A minimal Reanimated for Jest: only what the app uses. Entrances are inert
 * builders (chainable, recordable), animated views are plain views, and the
 * hooks behave like their static values. `useReducedMotion` is a jest.fn so a
 * test can turn «Reduce motion» on.
 */
import { View } from "react-native";

type Builder = { name: string; duration: (ms: number) => Builder; reduceMotion: (m: unknown) => Builder; ms?: number };

function builder(name: string): Builder {
  const b: Builder = {
    name,
    duration(ms) {
      return { ...b, ms };
    },
    reduceMotion() {
      return b;
    },
  };
  return b;
}

export const FadeIn = builder("FadeIn");
export const FadeInDown = builder("FadeInDown");
export const FadeOut = builder("FadeOut");
export const LinearTransition = builder("LinearTransition");
export const ReduceMotion = { System: "system", Always: "always", Never: "never" };

export const useReducedMotion = jest.fn(() => false);
export const useSharedValue = <T,>(v: T) => ({ value: v });
export const useAnimatedStyle = (fn: () => object) => fn();
export const withRepeat = jest.fn((v: unknown) => v);
export const withTiming = jest.fn((v: unknown) => v);
export const cancelAnimation = jest.fn();

const Animated = { View };
export default Animated;
