import { useEffect, useRef, useState } from "react";
import Animated, {
  Easing,
  FadeIn,
  FadeInDown,
  LinearTransition,
  ReduceMotion,
  useAnimatedProps,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withSequence,
  withTiming,
} from "react-native-reanimated";
import Svg, { Circle, Path } from "react-native-svg";

import { useSystemAppearance } from "@/theme/system-appearance";

/**
 * The design's micro-interactions (spec 069, R2.1, D5), as pieces every
 * screen can use. Each has its reduced-motion form (R2.5): the final state or
 * a plain fade, never a shorter wait for something that is not an animation.
 * Curves: the design's ease-out `cubic-bezier(.2,.8,.2,1)`; nothing bounces
 * and nothing runs past the 300 ms budget (R2.4).
 */
export function easeOut() {
  // Resolved when used, not at import: the test mock of Reanimated has no `bezier`.
  return typeof Easing.bezier === "function" ? Easing.bezier(0.2, 0.8, 0.2, 1) : Easing.out(Easing.cubic);
}

/** Times of the design (ms). */
export const MICRO = {
  /** Micro 2: the check's width, then its stroke. */
  checkGrow: 200,
  checkDraw: 160,
  checkDelay: 40,
  /** Micro 3: a row arriving, the others moving down, the badge beating once. */
  arrive: 200,
  beat: 240,
  /** Micro 4: a figure running to its value. */
  count: 240,
  /** Micro 5: content fading in over its skeleton. */
  fade: 160,
  /** Micro 8: the circle, then the check. */
  calmCircle: 240,
  calmCheckDelay: 340,
} as const;

const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

/** The check mark used by chips and lists: one path, 24 × 24, about 20 long. */
const CHECK = "M5 12.5l4.5 4.5L19 7.5";
const CHECK_LEN = 22;

/**
 * Micro 2 · a check that draws itself when it appears (a chosen chip, a chosen
 * time). Reduced motion: drawn at once.
 */
export function DrawCheck({ size = 14, color, strokeWidth = 2.2 }: { size?: number; color: string; strokeWidth?: number }) {
  const { reduceMotion } = useSystemAppearance();
  const offset = useSharedValue(reduceMotion ? 0 : CHECK_LEN);
  useEffect(() => {
    offset.value = reduceMotion
      ? 0
      : withDelay(MICRO.checkDelay, withTiming(0, { duration: MICRO.checkDraw, easing: Easing.out(Easing.quad), reduceMotion: ReduceMotion.Never }));
  }, [offset, reduceMotion]);
  const props = useAnimatedProps(() => ({ strokeDashoffset: offset.value }));
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" accessible={false} pointerEvents="none">
      <AnimatedPath
        d={CHECK}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={CHECK_LEN}
        animatedProps={props}
      />
    </Svg>
  );
}

/**
 * Micro 8 · an empty that reassures: a filled circle that draws in, then its
 * check (Inicio's «Todo en orden», empty lists that are good news). The demo
 * filled the disc at once and only drew the check; here both draw, as its guide
 * says. Reduced motion: drawn at once.
 */
export function CalmCheck({ size = 44, fill, ink }: { size?: number; fill: string; ink: string }) {
  const { reduceMotion } = useSystemAppearance();
  const circle = useSharedValue(reduceMotion ? 0 : 126);
  const check = useSharedValue(reduceMotion ? 0 : 26);
  const disc = useSharedValue(reduceMotion ? 1 : 0);
  useEffect(() => {
    if (reduceMotion) {
      circle.value = 0;
      check.value = 0;
      disc.value = 1;
      return;
    }
    circle.value = withDelay(100, withTiming(0, { duration: MICRO.calmCircle, easing: Easing.out(Easing.quad), reduceMotion: ReduceMotion.Never }));
    disc.value = withDelay(100 + MICRO.calmCircle - 80, withTiming(1, { duration: 160, reduceMotion: ReduceMotion.Never }));
    check.value = withDelay(MICRO.calmCheckDelay, withTiming(0, { duration: MICRO.checkDraw, easing: Easing.out(Easing.quad), reduceMotion: ReduceMotion.Never }));
  }, [circle, check, disc, reduceMotion]);
  const ringProps = useAnimatedProps(() => ({ strokeDashoffset: circle.value, fillOpacity: disc.value }));
  const checkProps = useAnimatedProps(() => ({ strokeDashoffset: check.value }));
  return (
    <Svg width={size} height={size} viewBox="0 0 48 48" accessible={false} pointerEvents="none">
      <AnimatedCircle cx={24} cy={24} r={20} stroke={fill} strokeWidth={3} fill={fill} strokeDasharray={126} animatedProps={ringProps} />
      <AnimatedPath
        d="M15 24.5l6 6L33 18"
        fill="none"
        stroke={ink}
        strokeWidth={3.2}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={26}
        animatedProps={checkProps}
      />
    </Svg>
  );
}

/**
 * Micro 4 · a figure runs from its previous value to the new one (balance,
 * the period's total). Returns the number to show; the screen reader should be
 * given the final value as the label, never the running one. Reduced motion:
 * the final value at once.
 */
export function useCountUp(value: number): number {
  const { reduceMotion } = useSystemAppearance();
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current;
    from.current = value;
    if (reduceMotion || start === value) {
      setShown(value);
      return;
    }
    let frame = 0;
    const t0 = Date.now();
    const tick = () => {
      const k = Math.min(1, (Date.now() - t0) / MICRO.count);
      const eased = 1 - (1 - k) ** 3;
      setShown(start + (value - start) * eased);
      if (k < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    // Whatever the frames did, the final value is written (the design's 300 ms guard).
    const guard = setTimeout(() => setShown(value), 300);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(guard);
    };
  }, [value, reduceMotion]);
  return shown;
}

/**
 * Micro 3 · the tab badge beats once when what you wait for arrives: an
 * animated style (scale 1 → 1.2 → 1 in 240 ms) that fires when `count` grows.
 * Reduced motion: no beat.
 */
export function useBeat(count: number) {
  const { reduceMotion } = useSystemAppearance();
  const scale = useSharedValue(1);
  const prev = useRef(count);
  useEffect(() => {
    if (count > prev.current && !reduceMotion) {
      scale.value = withSequence(
        withTiming(1.2, { duration: MICRO.beat / 2, easing: Easing.out(Easing.quad), reduceMotion: ReduceMotion.Never }),
        withTiming(1, { duration: MICRO.beat / 2, easing: Easing.out(Easing.quad), reduceMotion: ReduceMotion.Never }),
      );
    }
    prev.current = count;
  }, [count, reduceMotion, scale]);
  return useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
}

/**
 * Micro 3 · a row arriving at the top (it drops in 12 pt and fades in) and
 * the others making room. Reduced motion: a fade and no layout move.
 */
export function arrivalFor(reduced: boolean) {
  return {
    entering: reduced
      ? FadeIn.duration(MICRO.fade).reduceMotion(ReduceMotion.Never)
      : FadeInDown.duration(MICRO.arrive).easing(easeOut()).withInitialValues({ transform: [{ translateY: -12 }] }).reduceMotion(ReduceMotion.Never),
    layout: reduced ? undefined : LinearTransition.duration(MICRO.arrive).easing(easeOut()).reduceMotion(ReduceMotion.Never),
  };
}

export function useArrival() {
  return arrivalFor(useSystemAppearance().reduceMotion);
}

/** Micro 5 · content replacing its skeleton fades in (160 ms), the same with reduced motion. */
export const contentFade = FadeIn.duration(MICRO.fade).reduceMotion(ReduceMotion.Never);
