import { Image } from "expo-image";
import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import Animated from "react-native-reanimated";
import { SafeAreaView } from "react-native-safe-area-context";

import { useMotion } from "@/motion/use-motion";
import { useTheme } from "@/theme/theme";
import { Text } from "@/ui/text";

/**
 * The frame of the screens before the app proper: sign in, not a client, no
 * access, update. The brand mark, a title, a few lines, and the actions at the
 * bottom, within reach of the thumb. It scrolls when the text is at its largest.
 */
export function EntryFrame({
  title,
  body,
  lead,
  notice,
  children,
}: {
  title: string;
  body?: string;
  /** What reads with the body (a list it introduces), kept under it instead of pushed to the actions. */
  lead?: ReactNode;
  notice?: ReactNode;
  children: ReactNode;
}) {
  const { colors } = useTheme();
  const motion = useMotion();
  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: colors.background }]} edges={["top", "bottom"]}>
      {/* Follows the keyboard: the field in focus and the start of the next one stay in sight. */}
      <KeyboardAwareScrollView contentContainerStyle={styles.scroll} bounces={false} bottomOffset={112} keyboardShouldPersistTaps="handled">
        <Animated.View entering={motion.enter} style={styles.top}>
          <Image
            source={require("@/assets/images/mark.png")}
            tintColor={colors.primaryText}
            style={styles.mark}
            contentFit="contain"
            accessibilityIgnoresInvertColors
            accessible={false}
          />
          <Text variant="largeTitle" accessibilityRole="header">
            {title}
          </Text>
          {body ? (
            <Text variant="body" tone="mutedForeground">
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
    </SafeAreaView>
  );
}

/** A one-line message on an entry screen: what happened, in words. */
export function EntryNotice({ text, tone = "info" }: { text: string; tone?: "info" | "danger" }) {
  const { colors, radius } = useTheme();
  return (
    <View
      accessible
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[styles.notice, { backgroundColor: tone === "danger" ? colors.dangerBg : colors.infoBg, borderRadius: radius.md }]}
    >
      <Text variant="callout" tone={tone === "danger" ? "dangerText" : "infoText"}>
        {text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  scroll: { flexGrow: 1, justifyContent: "space-between", padding: 24, gap: 32 },
  top: { gap: 16, paddingTop: 32 },
  mark: { width: 56, height: 56 },
  bottom: { gap: 12 },
  notice: { padding: 12 },
});
