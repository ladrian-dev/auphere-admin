import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { AccessibilityInfo, Text as RNText } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ToastProvider, useToast, TOAST_MS, TOAST_UNDO_MS } from "@/ui/toast";

const metrics = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 47, left: 0, right: 0, bottom: 34 } };

/** Spec 044, research D7, R16.7: the brief notice. */
describe("the brief notice (R16.7, D7)", () => {
  function Trigger({ undo }: { undo?: () => void }) {
    const toast = useToast();
    return (
      <RNText
        onPress={() => toast.show({ text: "Reserva confirmada", action: undo ? { label: "Deshacer", onPress: undo } : undefined })}
      >
        go
      </RNText>
    );
  }

  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("says it to the screen reader and goes away after 4 s", async () => {
    const spoken = jest.spyOn(AccessibilityInfo, "announceForAccessibility");
    await render(
      <SafeAreaProvider initialMetrics={metrics}>
        <ToastProvider>
          <Trigger />
        </ToastProvider>
      </SafeAreaProvider>,
    );
    await act(async () => fireEvent.press(screen.getByText("go")));
    expect(screen.getByText("Reserva confirmada")).toBeTruthy();
    expect(spoken).toHaveBeenCalledWith("Reserva confirmada");
    expect(TOAST_MS).toBe(4000);
    await act(async () => jest.advanceTimersByTime(TOAST_MS + 50));
    expect(screen.queryByText("Reserva confirmada")).toBeNull();
  });

  it("with «Deshacer» it stays longer, and the action runs once", async () => {
    const undo = jest.fn();
    await render(
      <SafeAreaProvider initialMetrics={metrics}>
        <ToastProvider>
          <Trigger undo={undo} />
        </ToastProvider>
      </SafeAreaProvider>,
    );
    await act(async () => fireEvent.press(screen.getByText("go")));
    await act(async () => jest.advanceTimersByTime(TOAST_MS + 50));
    expect(screen.getByText("Deshacer")).toBeTruthy();
    expect(TOAST_UNDO_MS).toBeGreaterThanOrEqual(6000);
    await act(async () => fireEvent.press(screen.getByText("Deshacer")));
    expect(undo).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Reserva confirmada")).toBeNull();
  });
});

