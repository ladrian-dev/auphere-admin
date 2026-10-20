import { router, type Stack } from "expo-router";
import type { ComponentProps } from "react";
import { Platform } from "react-native";

import { useT } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { IconButton } from "@/ui/button";
import { icons } from "@/ui/icon";

type Options = Extract<ComponentProps<typeof Stack>["screenOptions"], object>;

/**
 * The platform's own header in the app's colours. The tint is for what you
 * tap (back, actions); the title stays in the text colour, as Material and
 * the iOS large title both do.
 */
export function useHeaderOptions(): Options {
  const { colors } = useTheme();
  return {
    headerShadowVisible: false,
    headerTintColor: colors.primaryText,
    headerTitleStyle: { color: colors.foreground },
    headerLargeTitleStyle: { color: colors.foreground },
    headerStyle: { backgroundColor: colors.background },
    headerLargeStyle: { backgroundColor: colors.background },
    contentStyle: { backgroundColor: colors.background },
  };
}

/** Each tab's stack: that header, large on iOS, and the way to Ajustes on the right. */
export function useTabStackOptions(): Options {
  const t = useT();
  return {
    ...useHeaderOptions(),
    headerLargeTitle: Platform.OS === "ios",
    headerRight: () => <SettingsButton label={t("app.settings.open")} />,
  };
}

function SettingsButton({ label }: { label: string }) {
  return <IconButton icon={icons.settings} label={label} onPress={() => router.push("/ajustes")} />;
}
