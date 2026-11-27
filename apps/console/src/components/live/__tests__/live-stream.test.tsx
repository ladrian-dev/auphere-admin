/**
 * Spec 082 — la línea en vivo de la consola, una por pestaña (3.11).
 *
 * `reservations.changed` deja vieja la agenda (una ráfaga es una relectura,
 * 1.7); un evento de conversación deja viejo el contador (3.7); al volver
 * tras un corte se relee todo y se avisa con `back` (3.10).
 */
import { act, render } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeEventSource } from "@/components/inbox/__tests__/view-harness";
import { keys } from "@/lib/query";
import { testQueryClient, withQuery } from "@/test/query";

import { LiveStreamProvider, useLiveStream, type LiveEvent } from "../live-stream";

const heard: LiveEvent[] = [];
function Ear() {
  const { subscribe } = useLiveStream();
  React.useEffect(() => subscribe((e) => heard.push(e)), [subscribe]);
  return null;
}

function mount(enabled = true) {
  const qc = testQueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  render(
    withQuery(
      <LiveStreamProvider enabled={enabled}>
        <Ear />
      </LiveStreamProvider>,
      qc,
    ),
  );
  return spy;
}
const invalidated = (spy: { mock: { calls: unknown[][] } }) =>
  spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));

beforeEach(() => {
  vi.useFakeTimers();
  heard.length = 0;
  FakeEventSource.last = null;
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("LiveStreamProvider", () => {
  it("abre una sola línea, en la ruta BFF de la Bandeja", () => {
    mount();
    expect(FakeEventSource.last?.url).toBe("/api/lite/inbox/stream");
  });

  it("sin módulos vivos no abre nada", () => {
    mount(false);
    expect(FakeEventSource.last).toBeNull();
  });

  it("una ráfaga de reservations.changed es una sola relectura de Reservas (1.7)", () => {
    const spy = mount();
    act(() => {
      for (let i = 0; i < 5; i++) FakeEventSource.last!.emit("reservations.changed", { event: "reservations.changed" });
    });
    expect(invalidated(spy)).toEqual([]);
    act(() => void vi.advanceTimersByTime(400));
    expect(invalidated(spy)).toEqual([JSON.stringify(keys.reservas)]);
  });

  it("un mensaje deja viejo el contador en menos de 2 s (3.7)", () => {
    const spy = mount();
    act(() => FakeEventSource.last!.emit("message.new", { event: "message.new", conversation_id: "c1", direction: "inbound" }));
    act(() => void vi.advanceTimersByTime(500));
    expect(invalidated(spy)).toEqual([JSON.stringify(keys.inboxCounts)]);
    expect(heard).toContainEqual({ name: "message.new", data: { event: "message.new", conversation_id: "c1", direction: "inbound" } });
  });

  it("al volver tras un corte relee Reservas y la Bandeja y avisa con back (3.10)", () => {
    const spy = mount();
    const es = FakeEventSource.last!;
    act(() => es.emit("ready", {}));
    expect(invalidated(spy)).toEqual([]);
    act(() => es.onerror?.());
    act(() => es.onerror?.());
    expect(heard.filter((e) => e.name === "down")).toHaveLength(1);
    act(() => es.emit("ready", {}));
    expect(invalidated(spy)).toEqual([JSON.stringify(keys.reservas), JSON.stringify(keys.inbox)]);
    expect(heard.at(-1)).toEqual({ name: "back" });
  });
});
