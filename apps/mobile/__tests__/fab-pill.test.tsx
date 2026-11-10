import { fireEvent, render, screen } from "@testing-library/react-native";
import { Platform, View } from "react-native";

import { tokens } from "@/theme/tokens.gen";


let mockGlass = false;
jest.mock("expo-glass-effect", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    isLiquidGlassAvailable: () => mockGlass,
    GlassView: (p: { children?: React.ReactNode; testID?: string }) => <RN.View testID="glass">{p.children}</RN.View>,
  };
});

const { Fab } = require("@/ui/fab") as typeof import("@/ui/fab");
const { Pill, pillOf } = require("@/ui/pill") as typeof import("@/ui/pill");
const { icons } = require("@/ui/icon") as typeof import("@/ui/icon");

/**
 * Spec 044, research D6, R5.1, R6.1, R16.4: the floating button and the state
 * pill Reservas adds to the app's kit.
 */
describe("the floating button (D6, R5.1, R6.1)", () => {
  it("is named for the screen reader and has a full target", async () => {
    const onPress = jest.fn();
    await render(<Fab icon={icons.plus} label="Llegada sin reserva" onPress={onPress} testID="fab" />);
    const b = screen.getByTestId("fab");
    expect(b.props.accessibilityLabel).toBe("Llegada sin reserva");
    await fireEvent.press(b);
    expect(onPress).toHaveBeenCalled();
  });

  it("is glass on iOS 26", async () => {
    mockGlass = true;
    await render(<Fab icon={icons.plus} label="Llegada sin reserva" onPress={() => undefined} />);
    expect(screen.getByTestId("glass")).toBeTruthy();
    mockGlass = false;
  });

  it("is an opaque circle without glass — never both", async () => {
    await render(<Fab icon={icons.plus} label="Llegada sin reserva" onPress={() => undefined} />);
    expect(screen.queryByTestId("glass")).toBeNull();
  });

  it("extended on Android, with its words visible", async () => {
    const os = jest.replaceProperty(Platform, "OS", "android");
    await render(<Fab icon={icons.calendarAdd} label="Nueva reserva" extended onPress={() => undefined} />);
    expect(screen.getByText("Nueva reserva")).toBeTruthy();
    os.restore();
  });
});

describe("the state of a reservation, in words (data-model.md)", () => {
  const t = (k: string, v?: Record<string, string | number>) => (v ? `${k}:${JSON.stringify(v)}` : k);

  it("names each state per mode, and a walk-in as «Sin reserva»", () => {
    expect(pillOf({ state: "pending", origin: "agent" }, "services", null, t as never).label).toBe("reservas.state.pending");
    expect(pillOf({ state: "done", origin: "agent" }, "services", null, t as never).label).toBe("reservas.state.done.services");
    expect(pillOf({ state: "done", origin: "agent" }, "capacity", null, t as never).label).toBe("reservas.state.done.capacity");
    expect(pillOf({ state: "arrived", origin: "walkin" }, "capacity", null, t as never).label).toBe("reservas.state.walkin");
  });

  it("puts «Llega tarde» over a still-expected one", () => {
    expect(pillOf({ state: "confirmed", origin: "agent" }, "capacity", 20, t as never).label).toBe('reservas.state.late:{"min":20}');
  });

  it("is never colour alone: it has its words, and the pending one a border", async () => {
    await render(
      <View>
        <Pill state="pending" origin="agent" mode="services" late={null} />
      </View>,
    );
    const pill = screen.getByTestId("pill-pending");
    expect(pill.props.style).toEqual(expect.arrayContaining([expect.objectContaining({ borderColor: tokens.light.warningSolid })]));
  });
});
