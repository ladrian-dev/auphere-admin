import { renderHook } from "@testing-library/react-native";
import { Platform } from "react-native";

import { useSheetOptions } from "@/features/sheets";
import { tokens } from "@/theme/tokens.gen";

/**
 * Spec 042 (T063, T066, T067, R1.7, R3.1, R3.3, D7): the two sheets. On iOS
 * they are form sheets that stop half way and rise to full height; with
 * Liquid Glass their container paints no background, so the system's sheet
 * material shows through; before iOS 26 the container is opaque, as it was.
 */
let mockGlass = false;
jest.mock("expo-glass-effect", () => ({ isLiquidGlassAvailable: () => mockGlass }));
jest.mock("expo-router", () => ({ Stack: {}, router: {} }));

afterEach(() => jest.restoreAllMocks());

it("iOS: Ajustes and the contact are form sheets with the same detents, a grabber and a transparent header", async () => {
  mockGlass = true;
  const { contacto, ajustes } = (await renderHook(() => useSheetOptions())).result.current;
  for (const o of [contacto, ajustes]) {
    expect(o.presentation).toBe("formSheet");
    expect(o.sheetAllowedDetents).toEqual([0.6, 1]);
    expect(o.sheetGrabberVisible).toBe(true);
    expect(o.contentStyle).toBeUndefined();
    expect(o.sheetCornerRadius).toBeUndefined();
  }
  expect(ajustes.headerShown).toBe(true);
});

it("iOS before 26: the same sheets, with the opaque container of today", async () => {
  mockGlass = false;
  const { contacto, ajustes } = (await renderHook(() => useSheetOptions())).result.current;
  expect(contacto.presentation).toBe("formSheet");
  expect((contacto.contentStyle as { backgroundColor?: string }).backgroundColor).toBe(tokens.light.background);
  expect((ajustes.contentStyle as { backgroundColor?: string }).backgroundColor).toBe(tokens.light.background);
});

it("Android: the contact is a Material bottom sheet with the app's corners; Ajustes is a screen", async () => {
  const os = jest.replaceProperty(Platform, "OS", "android");
  mockGlass = true; // never true on Android for real; the hook must not care
  const { contacto, ajustes } = (await renderHook(() => useSheetOptions())).result.current;
  expect(contacto.presentation).toBe("formSheet");
  expect(typeof contacto.sheetCornerRadius).toBe("number");
  expect(ajustes.presentation).toBe("card");
  expect((ajustes.contentStyle as { backgroundColor?: string }).backgroundColor).toBe(tokens.light.background);
  os.restore();
});
