import { act, renderHook } from "@testing-library/react-native";

import { useBizNow, useBizToday } from "@/api/reservas-hooks";
import type { ResConfig } from "@/api/reservas";

/**
 * Spec 044, research D3: «now» in the business moves with the phone's clock.
 * The first iOS pass found the «Ahora» line stuck at the minute it was read:
 * the hook memoised on the server's value and React Compiler kept it there.
 * The time it moves by is state now, so nothing can cache it away.
 */
beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date("2026-10-22T14:20:00Z")); // 11:20 in Santiago
});

afterEach(() => {
  jest.useRealTimers();
});

it("moves «now» on as the minutes pass, without a new read", async () => {
  const read = { date: "2026-10-22", minutes: 11 * 60 + 20, readAt: Date.now() };
  const { result } = await renderHook(() => useBizNow(read));
  expect(result.current).toEqual({ date: "2026-10-22", minutes: 11 * 60 + 20 });
  await act(async () => {
    jest.advanceTimersByTime(3 * 60_000);
  });
  expect(result.current).toEqual({ date: "2026-10-22", minutes: 11 * 60 + 23 });
});

it("turns the day at the business's midnight", async () => {
  jest.setSystemTime(new Date("2026-10-23T02:59:00Z")); // 23:59 in Santiago
  const config = { timezone: "America/Santiago" } as ResConfig;
  const { result } = await renderHook(() => useBizToday(config));
  expect(result.current).toBe("2026-10-22");
  await act(async () => {
    jest.advanceTimersByTime(60_000);
  });
  expect(result.current).toBe("2026-10-23");
});

it("the phone's clock is never older than the data it counts down (first iOS pass: «16 min» for a 15-minute offer)", async () => {
  const { useNowMs } = require("@/lib/use-now") as typeof import("@/lib/use-now");
  const readAt = Date.now() + 10_000; // the list arrived after the last tick
  const { result } = await renderHook(() => useNowMs(15_000, readAt));
  expect(result.current).toBe(readAt);
});
