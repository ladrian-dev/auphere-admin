import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { useInboxAutoclose } from "@/api/v13-ajustes-hooks";

/**
 * Spec 069, R17.2 (T038): the inactivity close is read and written with the
 * web's routes (`GET`/`PATCH /console/lite/inbox/settings`). What is chosen
 * shows at once; a refusal puts back what is stored.
 */
const mockRead = jest.fn();
const mockWrite = jest.fn();
jest.mock("@/api/v13-ajustes", () => ({
  ...jest.requireActual("@/api/v13-ajustes"),
  ajustesApi: { inboxSettings: () => mockRead(), setInboxSettings: (h: unknown) => mockWrite(h) },
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  mockRead.mockReset().mockResolvedValue({ autoclose_hours: null });
  mockWrite.mockReset();
});

it("without the Bandeja it reads nothing", async () => {
  const { result } = await renderHook(() => useInboxAutoclose(false), { wrapper });
  expect(result.current.state).toBe("off");
  expect(mockRead).not.toHaveBeenCalled();
});

it("reads what is stored and saves a choice", async () => {
  mockWrite.mockResolvedValue({ autoclose_hours: 24 });
  const { result } = await renderHook(() => useInboxAutoclose(true), { wrapper });
  await waitFor(() => expect(result.current.state).toBe("ready"));
  const ready = result.current as Extract<typeof result.current, { state: "ready" }>;
  expect(ready.hours).toBeNull();
  await act(async () => ready.save(24));
  expect(mockWrite).toHaveBeenCalledWith(24);
  expect(result.current).toMatchObject({ state: "ready", hours: 24, status: "saved" });
});

it("a refusal puts back what was stored and says it failed", async () => {
  mockRead.mockResolvedValue({ autoclose_hours: 72 });
  mockWrite.mockRejectedValue(new Error("422"));
  const { result } = await renderHook(() => useInboxAutoclose(true), { wrapper });
  await waitFor(() => expect(result.current.state).toBe("ready"));
  await act(async () => (result.current as Extract<typeof result.current, { state: "ready" }>).save(720));
  expect(result.current).toMatchObject({ state: "ready", hours: 72, status: "failed" });
});

it("a failed read is an error with its retry", async () => {
  mockRead.mockRejectedValue(new Error("500"));
  const { result } = await renderHook(() => useInboxAutoclose(true), { wrapper });
  await waitFor(() => expect(result.current.state).toBe("error"));
  mockRead.mockResolvedValue({ autoclose_hours: 168 });
  await act(async () => (result.current as Extract<typeof result.current, { state: "error" }>).retry());
  await waitFor(() => expect(result.current).toMatchObject({ state: "ready", hours: 168 }));
});

it("a value this version does not know is not said to be «Nunca»", async () => {
  mockRead.mockResolvedValue({ autoclose_hours: 48 });
  const { result } = await renderHook(() => useInboxAutoclose(true), { wrapper });
  await waitFor(() => expect(result.current.state).toBe("ready"));
  expect((result.current as Extract<typeof result.current, { state: "ready" }>).hours).toBeUndefined();
});
