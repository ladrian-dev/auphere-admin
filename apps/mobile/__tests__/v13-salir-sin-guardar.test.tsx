import { act, renderHook } from "@testing-library/react-native";
import { Alert } from "react-native";

/**
 * Spec 069 (R15.3), seen in the iOS simulator (T052): «Salir sin guardar» asked
 * again and again. Leaving dispatched the blocked action while the guard was
 * still on, so it blocked it once more. The guard must be off when it goes.
 */
let mockGuard: { on: boolean; cb: ((e: { data: { action: unknown } }) => void) | null } = { on: false, cb: null };
const mockDispatch = jest.fn();
const mockBack = jest.fn();
jest.mock("expo-router", () => ({
  router: { back: () => mockBack(), dismiss: jest.fn() },
  useNavigation: () => ({ dispatch: mockDispatch }),
  usePreventRemove: (on: boolean, cb: (e: { data: { action: unknown } }) => void) => {
    mockGuard = { on, cb };
  },
}));

const { useDiscardGuard } = require("@/features/reservas/discard-guard") as typeof import("@/features/reservas/discard-guard");

const t = (k: string) => k;

beforeEach(() => {
  mockDispatch.mockReset();
  mockBack.mockReset();
});

it("leaving from the system's own way out (a swipe, Android's back) goes, and does not ask again", async () => {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  await renderHook(() => useDiscardGuard(true, t as never));
  expect(mockGuard.on).toBe(true);
  const action = { type: "POP" };
  await act(async () => mockGuard.cb?.({ data: { action } }));
  const buttons = alert.mock.calls.at(-1)?.[2] as { style?: string; onPress?: () => void }[];
  await act(async () => buttons.find((b) => b.style === "destructive")?.onPress?.());
  expect(mockGuard.on).toBe(false);
  expect(mockDispatch).toHaveBeenCalledWith(action);
  expect(alert).toHaveBeenCalledTimes(1);
});

it("«Seguir aquí» stays, still guarded", async () => {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  await renderHook(() => useDiscardGuard(true, t as never));
  await act(async () => mockGuard.cb?.({ data: { action: { type: "POP" } } }));
  const buttons = alert.mock.calls.at(-1)?.[2] as { style?: string; onPress?: () => void }[];
  await act(async () => buttons.find((b) => b.style === "cancel")?.onPress?.());
  expect(mockGuard.on).toBe(true);
  expect(mockDispatch).not.toHaveBeenCalled();
});

it("the form's own close asks, then goes back once", async () => {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  const { result } = await renderHook(() => useDiscardGuard(true, t as never));
  await act(async () => result.current.close());
  const buttons = alert.mock.calls.at(-1)?.[2] as { style?: string; onPress?: () => void }[];
  await act(async () => buttons.find((b) => b.style === "destructive")?.onPress?.());
  expect(mockGuard.on).toBe(false);
  expect(mockBack).toHaveBeenCalledTimes(1);
});
