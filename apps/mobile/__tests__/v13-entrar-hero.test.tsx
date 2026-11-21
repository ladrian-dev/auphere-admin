import { render, screen, waitFor } from "@testing-library/react-native";
import { Text, TurboModuleRegistry } from "react-native";

/**
 * Spec 069 (R5.1, R5.2; console 066 R2.7, R2.8): the hero paints its still
 * ground first and the live liquid replaces it once loaded — only when the
 * binary carries Skia. Without it, or if loading fails, the still ground stays.
 */
let mockLoadFails = false;
jest.mock("@/features/entry/live-liquid", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  const LiveHero = ({ children }: { children: React.ReactNode }) => <RN.View testID="live-hero">{children}</RN.View>;
  return {
    get LiveHero() {
      // A module that throws as it loads (Skia's JavaScript without its native half, for instance).
      if (mockLoadFails) throw new Error("no Skia here");
      return LiveHero;
    },
  };
});

const hero = (LiquidHero: (p: { children: React.ReactNode }) => React.ReactNode) => (
  <LiquidHero>
    <Text>Tus clientes, siempre accesibles</Text>
  </LiquidHero>
);

afterEach(() => {
  jest.restoreAllMocks();
  mockLoadFails = false;
});

it("without Skia in the binary, the still ground, and nothing of Skia is loaded", async () => {
  jest.spyOn(TurboModuleRegistry, "get").mockReturnValue(null);
  const { LiquidHero } = require("@/features/entry/liquid-backdrop");
  await render(hero(LiquidHero));
  await waitFor(() => expect(screen.getByTestId("liquid-ground", { includeHiddenElements: true })).toBeTruthy());
  expect(screen.queryByTestId("live-hero")).toBeNull();
  expect(screen.getByText("Tus clientes, siempre accesibles")).toBeTruthy();
});

it("with Skia, the live liquid replaces the still ground once it is loaded", async () => {
  jest.spyOn(TurboModuleRegistry, "get").mockReturnValue({} as never);
  const { LiquidHero } = require("@/features/entry/liquid-backdrop");
  await render(hero(LiquidHero));
  await waitFor(() => expect(screen.getByTestId("live-hero")).toBeTruthy());
  expect(screen.getByText("Tus clientes, siempre accesibles")).toBeTruthy();
});

it("if the live layer fails to load, the still ground stays: never a hole, never an error", async () => {
  jest.spyOn(TurboModuleRegistry, "get").mockReturnValue({} as never);
  mockLoadFails = true;
  const { LiquidHero } = require("@/features/entry/liquid-backdrop");
  await render(hero(LiquidHero));
  await waitFor(() => expect(screen.getByTestId("liquid-ground", { includeHiddenElements: true })).toBeTruthy());
  expect(screen.queryByTestId("live-hero")).toBeNull();
  expect(screen.getByText("Tus clientes, siempre accesibles")).toBeTruthy();
});
