import type { TextProps } from "react-native";

import { useCountUp } from "@/motion/micro";
import type { TypeName } from "@/theme/type";
import type { Palette } from "@/theme/tokens.gen";
import { Text } from "@/ui/text";

/**
 * Micro 4 (spec 069, R18.3): an amount that runs from its previous value to
 * the new one in 240 ms, rounded to the currency's minor unit on every frame,
 * tabular. The screen reader is given the final value only, never a figure on
 * its way. With «Reducir movimiento» it is the final value at once.
 */
export function CountUpMoney({
  cents,
  format,
  variant = "figureLarge",
  tone = "foreground",
  ...rest
}: { cents: number; format: (cents: number) => string; variant?: TypeName; tone?: keyof Palette } & Pick<TextProps, "testID" | "accessible">) {
  const shown = Math.round(useCountUp(cents));
  return (
    <Text variant={variant} tone={tone} accessibilityLabel={format(cents)} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6} {...rest}>
      {format(shown)}
    </Text>
  );
}
