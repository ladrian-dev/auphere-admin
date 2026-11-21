import { createContext, use, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AccessibilityInfo, Platform, Pressable, StyleSheet, View } from "react-native";
import Animated, { Easing, ReduceMotion, useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useMotion } from "@/motion/use-motion";
import { RADII, TOUCH, useTheme } from "@/theme/theme";

import { Icon, icons, type IconName } from "./icon";
import { Text } from "./text";

/**
 * The brief notice (spec 044, R16.7, research D7): one sentence that says an
 * action whose result is not on screen went through — a reservation confirmed,
 * a walk-in registered, a note saved. One at a time; it is read out to the
 * screen reader and stays long enough to tap «Deshacer» when it offers it.
 * Opaque: it is a sentence, content, not a control floating on glass.
 *
 * Spec 069 (R2.1, micro 6): the inverse surface of the screen, an icon in its
 * tone, and — when it offers «Deshacer» — a thin bar that shows the time left.
 * The time stays 6 s (spec 044) rather than the demo's 4 s: more time to reach
 * «Deshacer» (WCAG 2.2.1). While it shows, floating buttons rise above it
 * (`useToastVisible`).
 */
export const TOAST_MS = 4000;
export const TOAST_UNDO_MS = 6000;
/** With VoiceOver or TalkBack on, reaching «Deshacer» takes much longer (review H10, WCAG 2.2.1). */
export const TOAST_UNDO_READER_MS = 20_000;

/** Whether a screen reader is on, and Android's «time to take action»; kept by `ToastProvider`. */
const reading = { on: false, recommendedMs: 0 };

/**
 * How long «Deshacer» lasts now. The notice and every write it can still stop
 * (Reservas' deferred cancel, `reservas-hooks.ts`) read the same value, so the
 * button never outlives the wait.
 */
export function undoMs(): number {
  return Math.max(reading.on ? TOAST_UNDO_READER_MS : TOAST_UNDO_MS, reading.recommendedMs);
}

function useReadingWatch(): void {
  useEffect(() => {
    let live = true;
    const set = (on: boolean) => {
      if (live) reading.on = on;
    };
    AccessibilityInfo.isScreenReaderEnabled()
      .then(set)
      .catch(() => undefined);
    const sub = AccessibilityInfo.addEventListener("screenReaderChanged", set);
    if (Platform.OS === "android" && typeof AccessibilityInfo.getRecommendedTimeoutMillis === "function") {
      AccessibilityInfo.getRecommendedTimeoutMillis(TOAST_UNDO_MS)
        .then((ms) => {
          if (live) reading.recommendedMs = ms;
        })
        .catch(() => undefined);
    }
    return () => {
      live = false;
      sub.remove();
    };
  }, []);
}

export type ToastTone = "ok" | "info" | "warn";
type Toast = { text: string; tone?: ToastTone; action?: { label: string; onPress: () => void } };
type Shown = Toast & { id: number; ms: number };
type Api = { show: (t: Toast) => void };

const Ctx = createContext<Api | null>(null);
const VisibleCtx = createContext(false);
const LiftCtx = createContext<((px: number) => void) | null>(null);

/**
 * Raise the toast above what floats at the bottom of this screen (the
 * conversation's dock), for as long as the screen is mounted (spec 069, R2.1, micro 6).
 */
export function useToastLift(px: number): void {
  const set = use(LiftCtx);
  useEffect(() => {
    if (!set) return;
    set(px);
    return () => set(0);
  }, [set, px]);
}

/** Whether a toast is on screen, so a floating button can rise above it (micro 6). */
export function useToastVisible(): boolean {
  return use(VisibleCtx);
}

const TONE_ICON: Record<ToastTone, IconName> = { ok: icons.circleCheck, info: icons.info, warn: icons.warning };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Shown | null>(null);
  const [lift, setLift] = useState(0);
  const seq = useRef(0);
  useReadingWatch();
  const show = useCallback((t: Toast) => {
    seq.current += 1;
    // The time is fixed when it shows, the same moment a deferred write reads it.
    setToast({ ...t, id: seq.current, ms: t.action ? undoMs() : TOAST_MS });
    // Said once, with its action, so the screen reader knows it can undo (review H10). iOS has no
    // live regions; on Android the notice's own live region says it (announcing is deprecated in 16).
    if (Platform.OS !== "android") AccessibilityInfo.announceForAccessibility(t.action ? `${t.text}. ${t.action.label}` : t.text);
  }, []);
  return (
    <Ctx value={{ show }}>
      <LiftCtx value={setLift}>
        <VisibleCtx value={toast !== null}>
          {children}
          {toast ? <ToastView key={toast.id} toast={toast} lift={lift} onDone={() => setToast(null)} /> : null}
        </VisibleCtx>
      </LiftCtx>
    </Ctx>
  );
}

export function useToast(): Api {
  const api = use(Ctx);
  if (!api) throw new Error("useToast outside ToastProvider");
  return api;
}

/** Above the tab bar: 49 pt on iOS, 80 dp on Android, plus a margin. */
const ABOVE_TABS = Platform.OS === "ios" ? 64 : 92;

function ToastView({ toast, lift, onDone }: { toast: Shown; lift: number; onDone: () => void }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const motion = useMotion();
  const ms = toast.ms;
  const left = useSharedValue(1);
  useEffect(() => {
    const id = setTimeout(onDone, ms);
    return () => clearTimeout(id);
  }, [toast, onDone, ms]);
  useEffect(() => {
    // The time left, linear; it is information, so it runs with reduced motion too.
    left.value = withTiming(0, { duration: ms, easing: Easing.linear, reduceMotion: ReduceMotion.Never });
  }, [left, ms]);
  const bar = useAnimatedStyle(() => ({ transform: [{ scaleX: left.value }] }));
  return (
    <View pointerEvents="box-none" style={[StyleSheet.absoluteFill, styles.layer, { paddingBottom: insets.bottom + (lift > 0 ? lift : ABOVE_TABS) }]}>
      <Animated.View
        entering={motion.enter}
        exiting={motion.exit}
        // Android says it from here, text and «Deshacer»; iOS from the announcement in `show` (never both).
        accessibilityLiveRegion={Platform.OS === "android" ? "polite" : undefined}
        testID="toast"
        style={[styles.toast, { backgroundColor: colors.toastBg, borderRadius: RADII.xl }]}
      >
        <View style={styles.row}>
          {toast.tone ? <Icon name={TONE_ICON[toast.tone]} size={18} tone="toastAccent" /> : null}
          <Text variant="callout" tone="toastFg" style={styles.text}>
            {toast.text}
          </Text>
          {toast.action ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                toast.action?.onPress();
                onDone();
              }}
              hitSlop={6}
              style={styles.action}
            >
              <Text variant="bodyStrong" tone="toastAccent">
                {toast.action.label}
              </Text>
            </Pressable>
          ) : null}
        </View>
        {toast.action ? (
          <View style={styles.track} importantForAccessibility="no-hide-descendants">
            <View style={[StyleSheet.absoluteFill, styles.trackGround, { backgroundColor: colors.toastFg }]} />
            <Animated.View style={[styles.bar, { backgroundColor: colors.toastAccent }, bar]} />
          </View>
        ) : null}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  layer: { justifyContent: "flex-end", paddingHorizontal: 16 },
  toast: { overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingLeft: 16, paddingRight: 8, minHeight: TOUCH },
  text: { flex: 1, minWidth: 0, paddingVertical: 12 },
  // The time left: a thin line at the bottom edge that empties from the end.
  track: { height: 3 },
  trackGround: { opacity: 0.16 },
  bar: { position: "absolute", left: 0, right: 0, top: 0, bottom: 0, transformOrigin: "left" },
  action: { minHeight: TOUCH, minWidth: TOUCH, justifyContent: "center", paddingHorizontal: 8 },
});
