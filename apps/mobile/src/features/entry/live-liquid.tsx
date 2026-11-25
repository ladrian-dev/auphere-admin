import { Canvas, Fill, Shader, Skia, type SkRuntimeEffect } from "@shopify/react-native-skia";
import { useIsFocused } from "expo-router/react-navigation";
import { useEffect, useState, type ReactNode } from "react";
import { AccessibilityInfo, AppState, StyleSheet, View, type LayoutChangeEvent } from "react-native";
import { GestureDetector, useManualGesture, type GestureTouchEvent } from "react-native-gesture-handler";
import Animated, { useFrameCallback, useSharedValue } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";

import { useMotion } from "@/motion/use-motion";

import { StillGround, type HeroProps } from "./liquid-backdrop";
import { framePace, liquidUniforms, stillUniforms, type LiquidUniforms } from "./liquid-pace";
import { LIQUID_SKSL, addWave, initialState, step, touch, type LiquidState } from "./liquid.gen";

/**
 * The living liquid (spec 069, D8, R5.1–R5.3, R22.4): the console's shader as
 * a Skia runtime effect, its uniforms in Reanimated shared values, the model's
 * `step()` in a frame callback on the UI thread and the finger from the
 * gesture handler — all of it on the UI thread, nothing on the JS one.
 *
 * - **It follows the finger and opens a wave where it lands** (R5.3). The
 *   gesture only observes the touches and never activates, so a drag that
 *   starts on the hero still scrolls the form above the keyboard.
 * - **It stands still** — one frame at `STILL_T`, deaf to the finger — with
 *   «Reducir movimiento» (R5.2), and for good when 30 frames in a row miss the
 *   50 fps budget after a short warm-up (R22.4, `framePace`). Until the setting is known it paints
 *   the still frame, so nothing moves for a few frames before it.
 * - **It stops** when the screen loses focus or the app leaves the foreground;
 *   it resumes where it was (its own clock, not the wall's).
 * - **It is decoration**: hidden from assistive tech, untouchable itself; the
 *   gesture belongs to the hero, never to the form (the card sits on top).
 *
 * The canvas is the hero's size in points (Skia's coordinates), and `R` with
 * it. Unlike the web it cannot draw at half resolution without an extra pass,
 * and the brief keeps the shader as it is.
 */
let effect: SkRuntimeEffect | null | undefined;

/** The compiled shader, once per process. `null` if Skia refuses it: the still ground stays. */
export function liquidEffect(): SkRuntimeEffect | null {
  if (effect === undefined) {
    try {
      effect = Skia.RuntimeEffect.Make(LIQUID_SKSL);
    } catch {
      effect = null;
    }
  }
  return effect;
}

export function LiveHero({ fallback, ...props }: HeroProps & { fallback: ReactNode }) {
  const source = liquidEffect();
  return source ? <Live source={source} {...props} /> : <>{fallback}</>;
}

/** «Reducir movimiento», followed live; `null` until the system has answered. */
function useReduceMotionSetting(): boolean | null {
  const [reduce, setReduce] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((v) => alive && setReduce(v))
      .catch(() => alive && setReduce(true));
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", (v) => setReduce(v));
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);
  return reduce;
}

function useForeground(): boolean {
  const [active, setActive] = useState(AppState.currentState === "active");
  useEffect(() => {
    const sub = AppState.addEventListener("change", (s) => setActive(s === "active"));
    return () => sub.remove();
  }, []);
  return active;
}

function Live({ source, style, children, testID }: HeroProps & { source: SkRuntimeEffect }) {
  const motion = useMotion();
  const focused = useIsFocused();
  const foreground = useForeground();
  const reduce = useReduceMotionSetting();
  const [frozen, setFrozen] = useState(false);
  const [size, setSize] = useState<[number, number] | null>(null);

  const state = useSharedValue<LiquidState>(initialState());
  /** Seconds of liquid time: advances only while it is drawn, so a pause resumes where it stopped. */
  const clock = useSharedValue(0);
  const slow = useSharedValue(0);
  /** Frames since it last started running: the warm-up of `framePace`. */
  const frames = useSharedValue(0);
  const box = useSharedValue<[number, number]>([1, 1]);
  const uniforms = useSharedValue<LiquidUniforms>(stillUniforms(1, 1, initialState()));

  // Unknown counts as reduced: nothing moves before the system has said it may.
  const still = frozen || reduce !== false;
  const running = !still && focused && foreground && size !== null;

  const frame = useFrameCallback((info) => {
    "worklet";
    const pace = framePace(slow.get(), info.timeSincePreviousFrame, frames.get());
    frames.set(frames.get() + 1);
    slow.set(pace.slow);
    const [w, h] = box.get();
    if (pace.freeze) {
      uniforms.set(stillUniforms(w, h, state.get()));
      scheduleOnRN(setFrozen, true);
      return;
    }
    const dt = Math.min(0.05, Math.max(0, (info.timeSincePreviousFrame ?? 0) / 1000));
    const t = clock.get() + dt;
    clock.set(t);
    state.modify((s) => {
      "worklet";
      step(s, t, dt);
      return s;
    }, false);
    uniforms.set(liquidUniforms(w, h, t, state.get()));
  }, false);

  useEffect(() => {
    if (running) {
      // Every start (focus, foreground) has its own warm-up and its own count.
      frames.set(0);
      slow.set(0);
    }
    frame.setActive(running);
  }, [frame, running, frames, slow]);

  // Still: one frame, repainted only when the box changes.
  useEffect(() => {
    if (still && size) uniforms.set(stillUniforms(size[0], size[1], state.get()));
  }, [still, size, uniforms, state]);

  const fingerAt = (e: GestureTouchEvent, wave: boolean) => {
    "worklet";
    const p = e.changedTouches[0];
    const [w, h] = box.get();
    if (!p || w <= 0 || h <= 0) return;
    // The model's coordinates: 0–1 on both axes, y upwards (the shader's).
    const x = p.x / w;
    const y = 1 - p.y / h;
    const t = clock.get();
    state.modify((s) => {
      "worklet";
      touch(s, x, y, t);
      if (wave) addWave(s, x, y, t, 1);
      return s;
    }, false);
  };
  const finger = useManualGesture({
    enabled: running,
    onTouchesDown: (e) => {
      "worklet";
      fingerAt(e, true);
    },
    onTouchesMove: (e) => {
      "worklet";
      fingerAt(e, false);
    },
  });

  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    box.set([width, height]);
    // The first frame the canvas paints is a still one of the right size; a live frame replaces it.
    uniforms.set(stillUniforms(width, height, state.get()));
    setSize([width, height]);
  };

  return (
    <GestureDetector gesture={finger}>
      <View style={[styles.hero, style]} onLayout={onLayout} testID={testID}>
        {/* Under the canvas until it has a size: the hero is never empty. */}
        <StillGround />
        {size ? (
          <Animated.View
            entering={motion.fade}
            style={StyleSheet.absoluteFill}
            pointerEvents="none"
            accessible={false}
            importantForAccessibility="no-hide-descendants"
            accessibilityElementsHidden
            testID="liquid-live"
          >
            <Canvas style={StyleSheet.absoluteFill} opaque pointerEvents="none" accessible={false} testID="liquid-canvas">
              <Fill>
                <Shader source={source} uniforms={uniforms} />
              </Fill>
            </Canvas>
          </Animated.View>
        ) : null}
        {children}
      </View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  hero: { overflow: "hidden" },
});
