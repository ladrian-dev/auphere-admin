import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { StyleSheet, TurboModuleRegistry, View, type StyleProp, type ViewStyle } from "react-native";
import Svg, { Defs, RadialGradient, Rect, Stop } from "react-native-svg";

import { themeFor } from "@/theme/theme";

/**
 * The hero of «Entrar» (spec 069, R5.1–R5.3, D8): the living liquid of the
 * console's sign-in (spec 066, requirement 2), drawn by Skia from the same
 * model and the same shader (`liquid.gen.ts`).
 *
 * The form never waits for it (066 R2.8): the hero first paints its still
 * ground — the brand's dark green with the liquid's two greens, a picture
 * drawn once — and the live layer replaces it as soon as it is loaded. If the
 * binary has no Skia (an older development client) or the shader does not
 * compile, the still ground stays: never a hole, never an error (066 R2.7).
 *
 * The live layer is a separate module loaded once the still ground is on
 * screen, so nothing of Skia, the gesture handler or the frame callback is
 * evaluated where Skia's native half is missing, and the first paint never
 * waits for Skia's JavaScript.
 */
/** The app's own frame budget (R22.4), next to the hero it governs; the rule itself lives in `liquid-pace.ts`. */
export { APP_SLOW_FRAME_MS } from "./liquid-pace";

export type HeroProps = { style?: StyleProp<ViewStyle>; children: ReactNode; testID?: string };
type LiveHero = ComponentType<HeroProps & { fallback: ReactNode }>;

/** Whether this binary carries Skia's native module (a dev client built before Skia was added does not). */
export function skiaInBinary(): boolean {
  try {
    return TurboModuleRegistry.get("RNSkiaModule") != null;
  } catch {
    return false;
  }
}

/** The live layer, or `null` when it cannot be: no Skia in the binary, or the module failed to load. */
function loadLiveHero(): LiveHero | null {
  if (!skiaInBinary()) return null;
  try {
    // A plain require, on purpose: evaluated only past the gate, bundled inline by Metro (no async
    // bundle in development), and run after the first paint.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return (require("./live-liquid") as { LiveHero: LiveHero }).LiveHero;
  } catch {
    return null; // the still ground stays
  }
}

export function LiquidHero(props: HeroProps) {
  const [Live, setLive] = useState<LiveHero | null>(null);
  useEffect(() => {
    // The frame after the still ground is on screen: the form never waits for Skia (066 R2.8).
    const id = requestAnimationFrame(() => {
      const live = loadLiveHero();
      if (live) setLive(() => live);
    });
    return () => cancelAnimationFrame(id);
  }, []);
  const still = <StillHero {...props} />;
  return Live ? <Live {...props} fallback={still} /> : still;
}

/** The hero with its still ground: the same box the live one has, so swapping them moves nothing. */
export function StillHero({ style, children, testID }: HeroProps) {
  return (
    <View style={[styles.hero, style]} testID={testID}>
      <StillGround />
      {children}
    </View>
  );
}

/**
 * The liquid as one still picture: the dark green ground with a mountain
 * meadow light high on the right and the deep green low on the left, where
 * the shader puts them. Decoration: hidden from assistive tech, untouchable.
 */
export function StillGround() {
  // The hero is the brand's own dark ground in both themes, so its colours are the brand's, not the scheme's.
  const brand = themeFor("light").colors;
  return (
    <View
      style={[StyleSheet.absoluteFill, { backgroundColor: brand.brandGround }]}
      pointerEvents="none"
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      testID="liquid-ground"
    >
      <Svg width="100%" height="100%" preserveAspectRatio="none" viewBox="0 0 100 100">
        <Defs>
          <RadialGradient id="meadow" cx="78" cy="22" r="62" gradientUnits="userSpaceOnUse">
            <Stop offset="0" stopColor={brand.highlight} stopOpacity={0.55} />
            <Stop offset="1" stopColor={brand.highlight} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id="deep" cx="18" cy="58" r="58" gradientUnits="userSpaceOnUse">
            <Stop offset="0" stopColor={brand.primary} stopOpacity={0.9} />
            <Stop offset="1" stopColor={brand.primary} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Rect x="0" y="0" width="100" height="100" fill="url(#deep)" />
        <Rect x="0" y="0" width="100" height="100" fill="url(#meadow)" />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: { overflow: "hidden" },
});
