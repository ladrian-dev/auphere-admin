import { useEffect, useState, type ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import Animated, { cancelAnimation, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from "react-native-reanimated";

import { useT } from "@/i18n/t";
import { useSystemAppearance } from "@/theme/system-appearance";
import { useTheme } from "@/theme/theme";

import { Button } from "./button";
import { Icon, icons, type IconName } from "./icon";
import { Text } from "./text";

/**
 * The five states (constitution §V, R14.1), one component each, all named for
 * assistive tech. None of them is a spinner in the middle of nothing.
 */

/** Shown only past 300 ms: a fast answer never flashes a skeleton (R14.1). */
export const SKELETON_DELAY_MS = 300;

export function Skeleton({ rows = 3, label }: { rows?: number; label?: string }) {
  const t = useT();
  const { colors, radius } = useTheme();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setVisible(true), SKELETON_DELAY_MS);
    return () => clearTimeout(id);
  }, []);
  return (
    <View
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={label ?? t("app.loading")}
      accessibilityState={{ busy: true }}
      testID="skeleton"
      style={styles.skeleton}
    >
      {visible
        ? Array.from({ length: rows }, (_, i) => (
            <View key={i} style={[styles.block, { backgroundColor: colors.muted, borderRadius: radius.md }]} testID="skeleton-row">
              <View style={[styles.line, { backgroundColor: colors.secondary, width: "40%" }]} />
              <View style={[styles.line, { backgroundColor: colors.secondary, width: "75%" }]} />
            </View>
          ))
        : null}
    </View>
  );
}

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: IconName;
  title: string;
  body?: string;
  action?: { label: string; onPress: () => void };
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.center}>
      {icon ? (
        <View style={[styles.badge, { backgroundColor: colors.muted }]}>
          <Icon name={icon} size={24} tone="mutedForeground" />
        </View>
      ) : null}
      <Text variant="headline" style={styles.centerText} accessibilityRole="header">
        {title}
      </Text>
      {body ? (
        <Text variant="callout" tone="mutedForeground" style={styles.centerText}>
          {body}
        </Text>
      ) : null}
      {action ? <Button label={action.label} variant="secondary" onPress={action.onPress} /> : null}
    </View>
  );
}

export function ErrorState({ title, body, onRetry }: { title?: string; body?: string; onRetry?: () => void }) {
  const t = useT();
  const { colors } = useTheme();
  return (
    <View style={styles.center}>
      <View style={[styles.badge, { backgroundColor: colors.dangerBg }]}>
        <Icon name={icons.warning} size={24} tone="dangerText" />
      </View>
      {/* The words are one alert; the retry stays its own button for the screen reader. */}
      <View accessible accessibilityRole="alert" style={styles.centerGroup}>
        <Text variant="headline" style={styles.centerText}>
          {title ?? t("app.error.title")}
        </Text>
        <Text variant="callout" tone="mutedForeground" style={styles.centerText}>
          {body ?? t("app.error.body")}
        </Text>
      </View>
      {onRetry ? <Button label={t("app.retry")} variant="secondary" icon={icons.retry} onPress={onRetry} /> : null}
    </View>
  );
}

/** R14.2: no network. What is on screen is the last thing that loaded. */
export function OfflineBanner({ since }: { since?: string | null }) {
  const t = useT();
  const { colors, radius } = useTheme();
  return (
    <View
      accessible
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[styles.banner, { backgroundColor: colors.warningBg, borderRadius: radius.md }]}
    >
      <Icon name={icons.offline} size={18} tone="warningText" />
      <View style={styles.bannerText}>
        <Text variant="subhead" tone="warningText">
          {t("app.offline")}
        </Text>
        {since ? (
          <Text variant="caption" tone="warningText">
            {t("app.stale", { time: since })}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

/** A part of the screen did not load: said once, above what did. */
export function PartialNotice({ text }: { text?: string }) {
  const t = useT();
  const { colors, radius } = useTheme();
  return (
    <View accessible accessibilityRole="alert" style={[styles.banner, { backgroundColor: colors.infoBg, borderRadius: radius.md }]}>
      <Icon name={icons.warning} size={18} tone="infoText" />
      <Text variant="subhead" tone="infoText" style={styles.bannerText}>
        {text ?? t("app.partial")}
      </Text>
    </View>
  );
}

/**
 * «Reconectando…» — the one animation allowed to loop (R14.9), and only while
 * the live line is down. With reduced motion it is a still dot (R14.7).
 */
export function ReconnectingIndicator({ label }: { label: string }) {
  const { colors } = useTheme();
  const reduced = useSystemAppearance().reduceMotion;
  const opacity = useSharedValue(1);
  useEffect(() => {
    if (reduced) {
      opacity.value = 1;
      return;
    }
    opacity.value = withRepeat(withTiming(0.35, { duration: 600 }), -1, true);
    return () => cancelAnimation(opacity);
  }, [reduced, opacity]);
  const dot = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return (
    <View accessibilityRole="text" accessibilityLabel={label} accessibilityLiveRegion="polite" style={styles.reconnecting}>
      <Animated.View testID="reconnecting-dot" style={[styles.dot, { backgroundColor: colors.warningSolid }, dot]} />
      <Text variant="caption" tone="warningText">
        {label}
      </Text>
    </View>
  );
}

/** A slot that keeps its place in a header row and lets its content wrap. */
export function Row({ children, gap = 8 }: { children: ReactNode; gap?: number }) {
  return <View style={[styles.row, { gap }]}>{children}</View>;
}

const styles = StyleSheet.create({
  skeleton: { gap: 12, paddingVertical: 8 },
  block: { padding: 16, gap: 10 },
  line: { height: 12, borderRadius: 4 },
  center: { alignItems: "center", justifyContent: "center", gap: 12, paddingHorizontal: 24, paddingVertical: 40 },
  centerText: { textAlign: "center", maxWidth: 420 },
  centerGroup: { alignItems: "center", gap: 12 },
  badge: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  banner: { flexDirection: "row", alignItems: "flex-start", gap: 10, padding: 12 },
  bannerText: { flex: 1, minWidth: 0, gap: 2 },
  reconnecting: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 24 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  row: { flexDirection: "row", alignItems: "center", flexWrap: "wrap" },
});
