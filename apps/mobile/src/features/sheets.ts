import { Platform } from "react-native";

import { useT } from "@/i18n/t";
import { glassAvailable } from "@/theme/glass";
import { SHEET_RADIUS, useTheme } from "@/theme/theme";

import { useHeaderOptions, type ScreenOptions as Options } from "./tab-stack";

/**
 * The two sheets of the app (spec 042, R1.7, R3.1, R3.3, D7): the contact of
 * a conversation and Ajustes. On iOS both are form sheets that stop at six
 * tenths and rise to full height, with the system's grabber. With Liquid
 * Glass the container paints nothing, so the sheet's own material shows
 * through and its header is transparent — the content respects the inset
 * with `contentInsetAdjustmentBehavior="automatic"` (spike S2, check 4).
 * Before iOS 26 the container is opaque, as it was. On Android the contact is
 * a Material bottom sheet with the app's corners and Ajustes is a screen.
 */
export function useSheetOptions(): { contacto: Options; ajustes: Options } {
  const t = useT();
  const { colors } = useTheme();
  const header = useHeaderOptions();
  const opaque: Options = glassAvailable() ? {} : { contentStyle: { backgroundColor: colors.background } };
  const sheet: Options = {
    presentation: "formSheet",
    sheetAllowedDetents: [0.6, 1],
    sheetGrabberVisible: true,
    // Android draws it square; iOS keeps the system's own corners.
    ...(Platform.OS === "android" ? { sheetCornerRadius: SHEET_RADIUS } : {}),
  };
  return {
    contacto: { ...sheet, ...opaque, headerShown: false },
    ajustes: {
      ...header,
      ...(Platform.OS === "ios" ? sheet : { presentation: "card" }),
      headerShown: true,
      title: t("app.settings"),
    },
  };
}
