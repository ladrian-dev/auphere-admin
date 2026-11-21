import { Image } from "expo-image";
import { GlassView } from "expo-glass-effect";
import { StatusBar } from "expo-status-bar";
import { use, type ReactNode } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import Animated from "react-native-reanimated";
import { SafeAreaInsetsContext, SafeAreaView } from "react-native-safe-area-context";

import { useT } from "@/i18n/t";
import { useMotion } from "@/motion/use-motion";
import { glassAvailable } from "@/theme/glass";
import { useSystemAppearance } from "@/theme/system-appearance";
import { RADII, useTheme } from "@/theme/theme";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * The frame of the screens before the app proper: not a client, no access,
 * update, the new password and the notices (spec 069, R3, R20.1, design §3.2–3.4).
 * The brand mark — or the screen's own tile or picture —, a title in the
 * display style (R1.4), a few lines, and the actions at the bottom, within
 * reach of the thumb. It scrolls when the text is at its largest.
 *
 * `footer` is pinned under what scrolls, always in sight, on an opaque bar
 * (the design's footbar): the notices screen puts its two answers there so
 * «Ahora no» is never below the fold on a 4,7″ phone (spec 044, R14.4; closes
 * 042 H15). `onBack` adds the round back button of the design, on glass where
 * the system draws it (a control, not content, R1.8).
 */
export function EntryFrame({
  title,
  body,
  lead,
  notice,
  footer,
  icon,
  art,
  onBack,
  center = false,
  children,
}: {
  title: string;
  body?: string;
  /** What reads with the body (a list it introduces), kept under it instead of pushed to the actions. */
  lead?: ReactNode;
  notice?: ReactNode;
  footer?: ReactNode;
  /** A tile with the screen's icon instead of the brand mark (partner, no access). */
  icon?: { name: IconName; tone?: "neutral" | "wait" };
  /** A picture instead of the mark (the new password's «Revisa tu correo»). */
  art?: ReactNode;
  onBack?: () => void;
  /** Centre the head (title and body) under a picture. */
  center?: boolean;
  children?: ReactNode;
}) {
  const { colors, scheme } = useTheme();
  const motion = useMotion();
  // Without a provider (a screen rendered alone, in a test) there is no inset.
  const bottomInset = use(SafeAreaInsetsContext)?.bottom ?? 0;
  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: colors.background }]} edges={footer ? ["top"] : ["top", "bottom"]}>
      {/* Over the sign-in's light bar: these screens sit on the page's own ground. */}
      <StatusBar style={scheme === "dark" ? "light" : "dark"} />
      {onBack ? (
        <View style={styles.bar}>
          <BackButton onPress={onBack} />
        </View>
      ) : null}
      {/* Follows the keyboard: the field in focus and the start of the next one stay in sight. */}
      <KeyboardAwareScrollView
        contentContainerStyle={styles.scroll}
        bounces={false}
        bottomOffset={112}
        keyboardShouldPersistTaps="handled"
        testID="entry-scroll"
      >
        <Animated.View entering={motion.enter} style={[styles.top, center ? styles.center : null]}>
          {art ?? (icon ? <IconTile name={icon.name} tone={icon.tone} /> : <BrandMark />)}
          <Text variant="screenTitle" accessibilityRole="header" style={center ? styles.centerText : null}>
            {title}
          </Text>
          {body ? (
            <Text variant="body" tone="mutedForeground" style={center ? styles.centerText : null}>
              {body}
            </Text>
          ) : null}
          {lead}
        </Animated.View>
        <View style={styles.bottom}>
          {notice}
          {children}
        </View>
      </KeyboardAwareScrollView>
      {footer ? (
        // Rides on the keyboard: the screen's action stays in sight while a field is edited; open, the
        // home-indicator inset is the keyboard's, so it is given back.
        <KeyboardStickyView offset={{ closed: 0, opened: bottomInset }}>
          <SafeAreaView edges={["bottom"]} style={[styles.footer, { backgroundColor: colors.card, borderTopColor: colors.border }]} testID="entry-footer">
            {footer}
          </SafeAreaView>
        </KeyboardStickyView>
      ) : null}
    </SafeAreaView>
  );
}

/** Auphere's isotype, in the brand's green. Decorative: the title says where you are. */
export function BrandMark({ size = 48 }: { size?: number }) {
  const { colors } = useTheme();
  return (
    <Image
      source={require("@/assets/images/mark.png")}
      tintColor={colors.primaryText}
      style={{ width: size, height: size }}
      contentFit="contain"
      accessibilityIgnoresInvertColors
      accessible={false}
    />
  );
}

/** The design's icon tile: a rounded square in a tint, the icon in its ink. «wait» is the amber of attention, not danger. */
export function IconTile({ name, tone = "neutral", size = 48 }: { name: IconName; tone?: "neutral" | "wait"; size?: number }) {
  const { colors } = useTheme();
  const wait = tone === "wait";
  return (
    <View
      style={[styles.tile, { width: size, height: size, borderRadius: RADII.md + 2, backgroundColor: wait ? colors.warningBg : colors.secondary }]}
      accessible={false}
      testID="entry-tile"
    >
      <Icon name={name} size={Math.round(size * 0.5)} tone={wait ? "warningText" : "foreground"} />
    </View>
  );
}

/**
 * Back, as the design draws it: a 44 pt circle with the chevron. On iOS 26 it
 * is Liquid Glass (a control); with «Reducir transparencia», before iOS 26 and
 * on Android it is an opaque circle with a defined edge.
 */
function BackButton({ onPress }: { onPress: () => void }) {
  const t = useT();
  const { colors } = useTheme();
  const { reduceTransparency } = useSystemAppearance();
  const glass = glassAvailable() && !reduceTransparency;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t("v13.entrar.back")}
      onPress={onPress}
      hitSlop={2}
      style={({ pressed }) => [
        styles.back,
        glass ? null : { backgroundColor: pressed ? colors.muted : colors.card, borderColor: colors.border, borderWidth: StyleSheet.hairlineWidth * 2 },
      ]}
    >
      {glass ? <GlassView glassEffectStyle="regular" isInteractive style={[StyleSheet.absoluteFill, styles.round]} /> : null}
      <Icon name={icons.back} size={22} tone="foreground" />
    </Pressable>
  );
}

/**
 * A short message on an entry screen: what happened, in words, with an icon
 * so it never rests on colour alone (R3.6). `offline` is the design's card
 * (R5.5): a title and the sentence, in the sunken tone.
 */
export function EntryNotice({ text, tone = "info" }: { text: string; tone?: "info" | "danger" | "offline" }) {
  const t = useT();
  const { colors } = useTheme();
  const bg = tone === "danger" ? colors.dangerBg : tone === "offline" ? colors.muted : colors.infoBg;
  const ink = tone === "danger" ? "dangerText" : tone === "offline" ? "foreground" : "infoText";
  const icon = tone === "danger" ? icons.failed : tone === "offline" ? icons.offline : icons.info;
  return (
    <View
      accessible
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[styles.notice, { backgroundColor: bg }]}
    >
      <Icon name={icon} size={20} tone={ink} />
      <View style={styles.noticeText}>
        {tone === "offline" ? (
          <Text variant="subhead" tone="foreground" style={styles.strong}>
            {t("v13.entrar.offline.title")}
          </Text>
        ) : null}
        <Text variant="callout" tone={tone === "offline" ? "mutedForeground" : ink}>
          {text}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  // Above what scrolls, inside the top safe area: the button never slides under the status bar.
  bar: { paddingHorizontal: 12, paddingTop: 4, alignItems: "flex-start" },
  scroll: { flexGrow: 1, justifyContent: "space-between", padding: 24, gap: 32 },
  top: { gap: 12, paddingTop: 16 },
  center: { alignItems: "center" },
  centerText: { textAlign: "center" },
  bottom: { gap: 12 },
  footer: { gap: 4, paddingHorizontal: 16, paddingTop: 10, paddingBottom: 8, borderTopWidth: StyleSheet.hairlineWidth },
  tile: { alignItems: "center", justifyContent: "center", borderCurve: "continuous" },
  back: { width: 44, height: 44, minWidth: 44, minHeight: 44, borderRadius: RADII.pill, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  round: { borderRadius: RADII.pill },
  notice: { flexDirection: "row", alignItems: "flex-start", gap: 12, padding: 14, borderRadius: RADII.md + 2, borderCurve: "continuous" },
  noticeText: { flex: 1, minWidth: 0, gap: 2 },
  strong: { fontWeight: "600" },
});
