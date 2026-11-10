import type { ReactNode } from "react";
import { Platform, View, type StyleProp, type ViewStyle } from "react-native";
import { ScrollViewMarker } from "react-native-screens/experimental";

type Edge = "automatic" | "hard" | "soft" | "hidden";

/**
 * The conversation's thread inside react-native-screens' `ScrollViewMarker`
 * (spec 042, H20): the marker applies the scroll-edge effects to its one
 * child — a `ScrollView` or a list, nothing in between — whenever that child
 * mounts. The screen's own `scrollEdgeEffects` option did not reach the
 * thread, most likely because it is applied when the options arrive and the
 * list only mounts once the conversation has loaded.
 *
 * The marker is compiled in because expo-router builds the library with
 * `RNS_GAMMA_ENABLED`. Android has no use for it: a plain view with the same
 * style.
 */
export function ContentScroll({
  edges = "automatic",
  style,
  children,
}: {
  /** The same effect on every edge; `hidden` turns the system's soft edge off. */
  edges?: Edge;
  style?: StyleProp<ViewStyle>;
  /** Exactly one scroll view: the marker reads its first child. */
  children: NonNullable<ReactNode>;
}) {
  if (Platform.OS !== "ios") return <View style={[{ flex: 1 }, style]}>{children}</View>;
  return (
    <ScrollViewMarker style={[{ flex: 1 }, style]} scrollEdgeEffects={{ top: edges, bottom: edges, left: edges, right: edges }}>
      {children}
    </ScrollViewMarker>
  );
}
