import { createContext, use, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AccessibilityInfo, Platform, Pressable, StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useMotion } from "@/motion/use-motion";
import { CARD_RADIUS, TOUCH, useTheme } from "@/theme/theme";

import { Text } from "./text";

/**
 * The brief notice (spec 044, R16.7, research D7): one sentence that says an
 * action whose result is not on screen went through — a reservation confirmed,
 * a walk-in registered, a note saved. One at a time; it is read out to the
 * screen reader and stays long enough to tap «Deshacer» when it offers it.
 * Opaque: it is a sentence, content, not a control floating on glass.
 */
export const TOAST_MS = 4000;
export const TOAST_UNDO_MS = 6000;

type Toast = { text: string; action?: { label: string; onPress: () => void } };
type Api = { show: (t: Toast) => void };

const Ctx = createContext<Api | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<(Toast & { id: number }) | null>(null);
  const seq = useRef(0);
  const show = useCallback((t: Toast) => {
    seq.current += 1;
    setToast({ ...t, id: seq.current });
    AccessibilityInfo.announceForAccessibility(t.text);
  }, []);
  return (
    <Ctx value={{ show }}>
      {children}
      {toast ? <ToastView key={toast.id} toast={toast} onDone={() => setToast(null)} /> : null}
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

function ToastView({ toast, onDone }: { toast: Toast; onDone: () => void }) {
  const { colors, scheme } = useTheme();
  const insets = useSafeAreaInsets();
  const motion = useMotion();
  useEffect(() => {
    const id = setTimeout(onDone, toast.action ? TOAST_UNDO_MS : TOAST_MS);
    return () => clearTimeout(id);
  }, [toast, onDone]);
  // The inverse surface of the palette: the text colour as the ground, the background as the text.
  const ground = scheme === "dark" ? colors.card : colors.foreground;
  const ink = scheme === "dark" ? "foreground" : "background";
  return (
    <View pointerEvents="box-none" style={[StyleSheet.absoluteFill, styles.layer, { paddingBottom: insets.bottom + ABOVE_TABS }]}>
      <Animated.View
        entering={motion.enter}
        exiting={motion.exit}
        accessibilityLiveRegion="polite"
        testID="toast"
        style={[styles.toast, { backgroundColor: ground, borderColor: colors.border, borderRadius: CARD_RADIUS }]}
      >
        <Text variant="callout" tone={ink} style={styles.text}>
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
            <Text variant="bodyStrong" tone={scheme === "dark" ? "primaryText" : "primary"}>
              {toast.action.label}
            </Text>
          </Pressable>
        ) : null}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  layer: { justifyContent: "flex-end", paddingHorizontal: 16 },
  toast: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingLeft: 16,
    paddingRight: 8,
    minHeight: TOUCH,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  text: { flex: 1, minWidth: 0, paddingVertical: 12 },
  action: { minHeight: TOUCH, minWidth: TOUCH, justifyContent: "center", paddingHorizontal: 8 },
});
