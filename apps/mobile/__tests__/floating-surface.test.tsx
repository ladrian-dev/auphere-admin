import { render, screen } from "@testing-library/react-native";
import { StyleSheet, Text, View } from "react-native";

import { tokens } from "@/theme/tokens.gen";
import { CARD_RADIUS } from "@/theme/theme";
import { FloatingSurface } from "@/ui/floating-surface";

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
