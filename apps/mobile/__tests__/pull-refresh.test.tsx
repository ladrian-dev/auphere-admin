import { act, renderHook } from "@testing-library/react-native";

import { usePullRefresh } from "@/lib/use-pull-refresh";

/**
 * Spec 044, first iOS pass: the pull-to-refresh spinner belongs to the
 * person's pull, not to every read the app does in the background.
 */
it("spins from the pull until its read is done, and not otherwise", async () => {
  let finish: () => void = () => undefined;
  const refetch = jest.fn(() => new Promise<void>((resolve) => (finish = resolve)));
  const { result } = await renderHook(() => usePullRefresh(refetch));
  expect(result.current.refreshing).toBe(false);

  await act(async () => result.current.onRefresh());
  expect(refetch).toHaveBeenCalledTimes(1);
  expect(result.current.refreshing).toBe(true);

  await act(async () => finish());
  expect(result.current.refreshing).toBe(false);
});

it("stops spinning when the read fails too", async () => {
  const { result } = await renderHook(() => usePullRefresh(() => Promise.reject(new Error("offline"))));
  await act(async () => result.current.onRefresh());
  expect(result.current.refreshing).toBe(false);
});
