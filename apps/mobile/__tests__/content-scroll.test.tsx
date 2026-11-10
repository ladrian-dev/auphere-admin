import { render, screen } from "@testing-library/react-native";
import { Platform, ScrollView, StyleSheet } from "react-native";

import { ContentScroll } from "@/ui/content-scroll";

/**
 * Spec 042 (H20): the thread inside react-native-screens' marker on iOS, with
 * the edge effects the screen asks for; on Android, a plain view with the
 * same style.
 */
jest.mock("react-native-screens/experimental", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    ScrollViewMarker: (p: { scrollEdgeEffects?: Record<string, string>; style?: unknown; children?: React.ReactNode }) => (
      <RN.View testID="scroll-view-marker" accessibilityHint={JSON.stringify(p.scrollEdgeEffects)} style={p.style as never}>
        {p.children}
      </RN.View>
    ),
  };
});

it("iOS: the scroll view is the marker's only child, with automatic edges by default", async () => {
  await render(
    <ContentScroll>
      <ScrollView testID="list" />
    </ContentScroll>,
  );
  const marker = screen.getByTestId("scroll-view-marker");
  expect(JSON.parse(marker.props.accessibilityHint)).toEqual({ top: "automatic", bottom: "automatic", left: "automatic", right: "automatic" });
  expect(StyleSheet.flatten(marker.props.style).flex).toBe(1);
  expect(screen.getByTestId("list")).toBeTruthy();
});

it("iOS: the conversation hides every edge (H20)", async () => {
  await render(
    <ContentScroll edges="hidden" style={{ marginTop: 100 }}>
      <ScrollView />
    </ContentScroll>,
  );
  const marker = screen.getByTestId("scroll-view-marker");
  expect(JSON.parse(marker.props.accessibilityHint).top).toBe("hidden");
  expect(StyleSheet.flatten(marker.props.style).marginTop).toBe(100);
});

it("Android: no marker, the same layout", async () => {
  const os = jest.replaceProperty(Platform, "OS", "android");
  await render(
    <ContentScroll style={{ marginTop: 0 }}>
      <ScrollView testID="list" />
    </ContentScroll>,
  );
  expect(screen.queryByTestId("scroll-view-marker")).toBeNull();
  expect(screen.getByTestId("list")).toBeTruthy();
  os.restore();
});
