import { Text as RNText, type TextProps } from "react-native";

import { useTheme } from "@/theme/theme";
import { type, type TypeName } from "@/theme/type";
import type { Palette } from "@/theme/tokens.gen";

/**
 * Text with a type style and a colour role. Scales with the system text size
 * (R14.4): never `allowFontScaling={false}`, never a fixed line count unless
 * the caller asks for one.
 */
export function Text({
  variant = "body",
  tone = "foreground",
  style,
  ...rest
}: TextProps & { variant?: TypeName; tone?: keyof Palette }) {
  const { colors } = useTheme();
  return <RNText {...rest} style={[type[variant], { color: colors[tone] }, style]} />;
}
