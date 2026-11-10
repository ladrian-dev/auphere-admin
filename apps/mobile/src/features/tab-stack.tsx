import { router, Stack } from "expo-router";
import type { ComponentProps } from "react";
import { Platform, useWindowDimensions } from "react-native";

import { useT } from "@/i18n/t";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { headerSize, type } from "@/theme/type";
import { IconButton } from "@/ui/button";
import { icons } from "@/ui/icon";

/** A stack screen's options as a plain object (not the function form `screenOptions` also takes). */
export type ScreenOptions = Exclude<Extract<ComponentProps<typeof Stack>["screenOptions"], object>, (...a: never[]) => unknown>;
type Options = ScreenOptions;

/**
 * The platform's own header in the app's colours (spec 042, R1.1, R3.1, D1).
 * The tint is for what you tap (back, actions); the title stays in the text
 * colour, as Material and the iOS large title both do.
 *
 * On iOS 26 with Liquid Glass the bar is the system's: no background of its
 * own, the content scrolls under it and the system draws the scroll-edge
 * effect. Painting a background there turns the glass off — and makes the
 * large title invisible (react-native-screens warns about exactly that; H14).
 * Before iOS 26 and on Android the bar is opaque, as it always was.
 */
export function useHeaderOptions(): Options {
  const { colors } = useTheme();
  const { fontScale } = useWindowDimensions();
  // iOS: the large title follows the phone's text size by Apple's own table (R4.6, H8); the inline title stays
  // fixed, as Apple keeps it (the bar cannot grow). Android scales its sp itself.
  const base: Options = {
    headerShadowVisible: false,
    headerTintColor: colors.primaryText,
    headerTitleStyle: { color: colors.foreground },
    headerLargeTitleStyle: { color: colors.foreground, ...(Platform.OS === "ios" ? { fontSize: headerSize("largeTitle", fontScale) } : {}) },
  };
  if (glassAvailable()) return base;
  return {
    ...base,
    // Android's toolbar sizes its title in sp only when told a size (R4.6, D14).
    ...(Platform.OS === "android" ? { headerTitleStyle: { color: colors.foreground, fontSize: type.title.fontSize } } : {}),
    headerStyle: { backgroundColor: colors.background },
    headerLargeStyle: { backgroundColor: colors.background },
    contentStyle: { backgroundColor: colors.background },
  };
}

/**
 * Each tab's stack: that header, large on iOS. The way to Ajustes is a native
 * bar button on iOS (`SettingsToolbar`, grouped in glass on iOS 26) and a
 * `headerRight` button on Android (R1.4).
 */
export function useTabStackOptions(): Options {
  const t = useT();
  const header = useHeaderOptions();
  if (Platform.OS === "ios") return { ...header, headerLargeTitleEnabled: true };
  return { ...header, headerRight: () => <SettingsButton label={t("app.settings.open")} /> };
}

/** Rendered by each tab's screen: on iOS the system's own bar button for Ajustes; nothing on Android. */
export function SettingsToolbar() {
  const t = useT();
  const { colors } = useTheme();
  if (Platform.OS !== "ios") return null;
  // The bar button does not inherit `headerTintColor`: the one accent colour goes on explicitly (R1.6).
  return (
    <Stack.Toolbar placement="right">
      <Stack.Toolbar.Button
        icon={icons.settings.ios}
        tintColor={colors.primaryText}
        accessibilityLabel={t("app.settings.open")}
        onPress={() => router.push("/ajustes")}
      />
    </Stack.Toolbar>
  );
}

function SettingsButton({ label }: { label: string }) {
  return <IconButton icon={icons.settings} label={label} onPress={() => router.push("/ajustes")} />;
}
