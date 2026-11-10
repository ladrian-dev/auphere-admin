import { act, renderHook } from "@testing-library/react-native";
import { AccessibilityInfo, Platform } from "react-native";

import { useSystemAppearance } from "@/theme/system-appearance";

/**
 * Spec 042 (T020, R4.5): the three settings the material reacts to — «Reducir
 * transparencia», «Aumentar contraste» (or Android's high contrast) and
 * «Reducir movimiento» — read at mount and followed live, never only at
 * launch.
 */
type Handler = (enabled: boolean) => void;
let listeners: Record<string, Handler>;
let removes: jest.Mock[];

function stub(values: Partial<Record<"transparency" | "darker" | "highContrast" | "motion", boolean>> = {}) {
  listeners = {};
  removes = [];
  jest.spyOn(AccessibilityInfo, "isReduceTransparencyEnabled").mockResolvedValue(values.transparency ?? false);
  jest.spyOn(AccessibilityInfo, "isDarkerSystemColorsEnabled").mockResolvedValue(values.darker ?? false);
  jest.spyOn(AccessibilityInfo, "isHighTextContrastEnabled").mockResolvedValue(values.highContrast ?? false);
  jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(values.motion ?? false);
  jest.spyOn(AccessibilityInfo, "addEventListener").mockImplementation(((event: string, handler: Handler) => {
    listeners[event] = handler;
    const remove = jest.fn(() => {
      delete listeners[event];
    });
    removes.push(remove);
    return { remove };
  }) as never);
}

afterEach(() => jest.restoreAllMocks());

it("reads the phone's settings at mount (iOS: transparency, darker colours, motion)", async () => {
  stub({ transparency: true, darker: true, motion: true });
  const { result } = await renderHook(() => useSystemAppearance());
  await act(async () => undefined);
  expect(result.current).toEqual({ reduceTransparency: true, increaseContrast: true, reduceMotion: true });
});

it("follows the settings live: a change with the app open re-renders (R4.5)", async () => {
  stub();
  const { result } = await renderHook(() => useSystemAppearance());
  await act(async () => undefined);
  expect(result.current.reduceTransparency).toBe(false);
  await act(async () => listeners["reduceTransparencyChanged"]!(true));
  expect(result.current.reduceTransparency).toBe(true);
  await act(async () => listeners["darkerSystemColorsChanged"]!(true));
  expect(result.current.increaseContrast).toBe(true);
  await act(async () => listeners["reduceMotionChanged"]!(true));
  expect(result.current.reduceMotion).toBe(true);
});

it("on Android, «Aumentar contraste» is the system's high text contrast", async () => {
  const os = jest.replaceProperty(Platform, "OS", "android");
  stub({ highContrast: true, darker: true });
  const { result } = await renderHook(() => useSystemAppearance());
  await act(async () => undefined);
  expect(result.current.increaseContrast).toBe(true);
  expect(listeners["highTextContrastChanged"]).toBeDefined();
  expect(listeners["darkerSystemColorsChanged"]).toBeUndefined();
  os.restore();
});

it("lets go of every listener when it unmounts", async () => {
  stub();
  const { unmount } = await renderHook(() => useSystemAppearance());
  await act(async () => undefined);
  expect(removes.length).toBeGreaterThanOrEqual(3);
  await unmount();
  for (const remove of removes) expect(remove).toHaveBeenCalled();
});
