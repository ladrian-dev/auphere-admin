import { fireEvent, render, screen } from "@testing-library/react-native";
import { StyleSheet, Text, View } from "react-native";

import { tokens } from "@/theme/tokens.gen";
import { CARD_RADIUS } from "@/theme/theme";
import { FOOT_GAP, FOOT_MAX_SHARE, FloatingSurface } from "@/ui/floating-surface";

/**
 * Spec 042 (T021, T072, R2.1, R3.1, R3.3, R4.2, R4.3, R4.5): one surface for
 * the foot of a conversation. Glass where the system has it and the person
 * allows it; otherwise the opaque, docked foot of the 031 — same code, two
 * presentations. Never a drop in opacity.
 */
let mockGlass = true;
let mockAppearance = { reduceTransparency: false, increaseContrast: false, reduceMotion: false };
jest.mock("expo-glass-effect", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    isLiquidGlassAvailable: () => mockGlass,
    GlassView: (p: Record<string, unknown>) => <RN.View testID="glass-view" {...p} />,
  };
});
jest.mock("@/theme/system-appearance", () => ({ useSystemAppearance: () => mockAppearance }));

const flat = (id: string) => StyleSheet.flatten(screen.getByTestId(id).props.style) as Record<string, unknown>;

beforeEach(() => {
  mockGlass = true;
  mockAppearance = { reduceTransparency: false, increaseContrast: false, reduceMotion: false };
});

it("with glass available it floats: a GlassView with side margins and a radius, no border", async () => {
  await render(
    <FloatingSurface testID="surface">
      <Text>hola</Text>
    </FloatingSurface>,
  );
  expect(screen.getByTestId("glass-view")).toBeTruthy();
  const style = flat("surface");
  expect(style.marginHorizontal).toBe(12);
  expect(style.borderRadius).toBe(CARD_RADIUS);
  expect(style.borderTopWidth).toBeUndefined();
  expect(style.opacity).toBeUndefined();
});

it("without glass it is the docked foot of the 031: opaque, full width, no radius, a hairline on top", async () => {
  mockGlass = false;
  await render(
    <FloatingSurface testID="surface">
      <Text>hola</Text>
    </FloatingSurface>,
  );
  expect(screen.queryByTestId("glass-view")).toBeNull();
  const style = flat("surface");
  expect(style.backgroundColor).toBe(tokens.light.card);
  expect(style.marginHorizontal).toBeUndefined();
  expect(style.borderRadius).toBeUndefined();
  expect(style.borderTopWidth).toBe(StyleSheet.hairlineWidth);
  expect(style.borderTopColor).toBe(tokens.light.border);
  expect(style.opacity).toBeUndefined();
});

it("«Reducir transparencia» wins over the glass: opaque and docked, the app decides (R4.2)", async () => {
  mockAppearance = { ...mockAppearance, reduceTransparency: true };
  await render(
    <FloatingSurface testID="surface">
      <Text>hola</Text>
    </FloatingSurface>,
  );
  expect(screen.queryByTestId("glass-view")).toBeNull();
  expect(flat("surface").backgroundColor).toBe(tokens.light.card);
});

it("«Aumentar contraste» draws a defined border all round (R4.3)", async () => {
  mockAppearance = { ...mockAppearance, increaseContrast: true };
  await render(
    <FloatingSurface testID="surface">
      <Text>hola</Text>
    </FloatingSurface>,
  );
  const style = flat("surface");
  expect(style.borderWidth).toBe(1);
  expect(style.borderColor).toBe(tokens.light.border);
});

it("tone=warning tints the border, never the surface itself", async () => {
  await render(
    <FloatingSurface testID="surface" tone="warning">
      <Text>hola</Text>
    </FloatingSurface>,
  );
  const style = flat("surface");
  expect(style.borderColor).toBe(tokens.light.warningSolid);
  expect(style.backgroundColor).toBeUndefined();
});

describe("it animates its own height (spike S2, T056, R2.5, R2.6)", () => {
  const Reanimated = require("react-native-reanimated") as { withTiming: jest.Mock };
  const { durations } = require("@/motion/durations") as { durations: { state: number } };
  beforeEach(() => Reanimated.withTiming.mockClear());

  it("the first measure sets the height; the next ones go through withTiming at durations.state", async () => {
    await render(
      <FloatingSurface testID="surface">
        <Text>hola</Text>
      </FloatingSurface>,
    );
    const content = screen.getByTestId("surface-content");
    await fireEvent(content, "layout", { nativeEvent: { layout: { height: 180 } } });
    expect(Reanimated.withTiming).not.toHaveBeenCalled();
    await fireEvent(content, "layout", { nativeEvent: { layout: { height: 72 } } });
    // Floating, no inset: the clearance is the content plus the 8 pt margin and the gap.
    expect(Reanimated.withTiming).toHaveBeenCalledWith(72 + 8 + FOOT_GAP, expect.objectContaining({ duration: durations.state }));
  });

  it("with «Reducir movimiento» the height changes without animating", async () => {
    mockAppearance = { ...mockAppearance, reduceMotion: true };
    await render(
      <FloatingSurface testID="surface">
        <Text>hola</Text>
      </FloatingSurface>,
    );
    const content = screen.getByTestId("surface-content");
    await fireEvent(content, "layout", { nativeEvent: { layout: { height: 180 } } });
    await fireEvent(content, "layout", { nativeEvent: { layout: { height: 72 } } });
    expect(Reanimated.withTiming).not.toHaveBeenCalled();
  });

  it("writes the clearance into the shared value the screen hands it — content, border, floating margin and gap — and keeps its own height to the content", async () => {
    const { useSharedValue } = require("react-native-reanimated") as { useSharedValue: <T>(v: T) => { value: T } };
    const shared = useSharedValue(0) as unknown as import("react-native-reanimated").SharedValue<number>;
    await render(
      <FloatingSurface testID="surface" clearance={shared} bottomInset={34} tone="warning">
        <Text>hola</Text>
      </FloatingSurface>,
    );
    await fireEvent(screen.getByTestId("surface-content"), "layout", { nativeEvent: { layout: { height: 180 } } });
    expect(shared.value).toBe(180 + 2 + 34 + 8 + FOOT_GAP);
  });

  it("never takes more than its share of the window: past it, the clearance stops and the content scrolls inside (R4.7)", async () => {
    const { Dimensions } = require("react-native") as typeof import("react-native");
    const dims = jest.spyOn(Dimensions, "get").mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 3.1 });
    const { useSharedValue } = require("react-native-reanimated") as { useSharedValue: <T>(v: T) => { value: T } };
    const shared = useSharedValue(0) as unknown as import("react-native-reanimated").SharedValue<number>;
    await render(
      <FloatingSurface testID="surface" clearance={shared}>
        <Text>hola</Text>
      </FloatingSurface>,
    );
    await fireEvent(screen.getByTestId("surface-content"), "layout", { nativeEvent: { layout: { height: 300 } } });
    expect(screen.getByTestId("surface-scroll").props.scrollEnabled).toBe(false);
    await fireEvent(screen.getByTestId("surface-content"), "layout", { nativeEvent: { layout: { height: 900 } } });
    expect(shared.value).toBe(Math.round(844 * FOOT_MAX_SHARE) + 8 + FOOT_GAP);
    expect(screen.getByTestId("surface-scroll").props.scrollEnabled).toBe(true);
    dims.mockRestore();
  });

  it("also hands the clearance to the screen as a number each time it settles, for a list padded in React state (H20)", async () => {
    const onClearance = jest.fn();
    await render(
      <FloatingSurface testID="surface" bottomInset={34} onClearance={onClearance}>
        <Text>hola</Text>
      </FloatingSurface>,
    );
    await fireEvent(screen.getByTestId("surface-content"), "layout", { nativeEvent: { layout: { height: 180 } } });
    expect(onClearance).toHaveBeenLastCalledWith(180 + 34 + 8 + FOOT_GAP);
    await fireEvent(screen.getByTestId("surface-content"), "layout", { nativeEvent: { layout: { height: 72 } } });
    expect(onClearance).toHaveBeenLastCalledWith(72 + 34 + 8 + FOOT_GAP);
  });

  it("docked, the clearance is the content (with its inset padding) and the gap", async () => {
    mockGlass = false;
    const { useSharedValue } = require("react-native-reanimated") as { useSharedValue: <T>(v: T) => { value: T } };
    const shared = useSharedValue(0) as unknown as import("react-native-reanimated").SharedValue<number>;
    await render(
      <FloatingSurface testID="surface" clearance={shared} bottomInset={34}>
        <Text>hola</Text>
      </FloatingSurface>,
    );
    await fireEvent(screen.getByTestId("surface-content"), "layout", { nativeEvent: { layout: { height: 214 } } });
    expect(shared.value).toBe(214 + FOOT_GAP);
  });
});

it("a change of «Reducir transparencia» with the surface mounted swaps the material without remounting the children (T072, R4.5)", async () => {
  const { rerender } = await render(
    <FloatingSurface testID="surface">
      <View testID="child" />
    </FloatingSurface>,
  );
  const before = screen.getByTestId("child");
  mockAppearance = { ...mockAppearance, reduceTransparency: true };
  await rerender(
    <FloatingSurface testID="surface">
      <View testID="child" />
    </FloatingSurface>,
  );
  expect(screen.queryByTestId("glass-view")).toBeNull();
  expect(screen.getByTestId("child")).toBe(before);
});
