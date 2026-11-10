import { useEffect, useState } from "react";
import { AccessibilityInfo, Platform } from "react-native";

/**
 * The three settings the material reacts to (spec 042, R4.2, R4.3, R4.5, D5):
 * «Reducir transparencia» and «Aumentar contraste» on iOS, the high text
 * contrast on Android, and «Reducir movimiento» on both. Read at mount and
 * followed live — Reanimated's own `useReducedMotion` only knows the value at
 * launch.
 */
export type SystemAppearance = {
  reduceTransparency: boolean;
  increaseContrast: boolean;
  reduceMotion: boolean;
};

const initial: SystemAppearance = { reduceTransparency: false, increaseContrast: false, reduceMotion: false };

export function useSystemAppearance(): SystemAppearance {
  const [state, setState] = useState(initial);
  useEffect(() => {
    let alive = true;
    const set = (patch: Partial<SystemAppearance>) => {
      if (alive) setState((s) => ({ ...s, ...patch }));
    };
    const ios = Platform.OS === "ios";
    void AccessibilityInfo.isReduceMotionEnabled().then((v) => set({ reduceMotion: v }));
    if (ios) {
      void AccessibilityInfo.isReduceTransparencyEnabled().then((v) => set({ reduceTransparency: v }));
      void AccessibilityInfo.isDarkerSystemColorsEnabled().then((v) => set({ increaseContrast: v }));
    } else {
      void AccessibilityInfo.isHighTextContrastEnabled().then((v) => set({ increaseContrast: v }));
    }
    const subscriptions = [
      AccessibilityInfo.addEventListener("reduceMotionChanged", (v) => set({ reduceMotion: v })),
      ...(ios
        ? [
            AccessibilityInfo.addEventListener("reduceTransparencyChanged", (v) => set({ reduceTransparency: v })),
            AccessibilityInfo.addEventListener("darkerSystemColorsChanged", (v) => set({ increaseContrast: v })),
          ]
        : [AccessibilityInfo.addEventListener("highTextContrastChanged", (v) => set({ increaseContrast: v }))]),
    ];
    return () => {
      alive = false;
      for (const s of subscriptions) s.remove();
    };
  }, []);
  return state;
}
