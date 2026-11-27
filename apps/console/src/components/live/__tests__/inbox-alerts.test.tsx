/**
 * Spec 082, Historia 3 — la Bandeja avisa esté donde esté la persona.
 *
 * Suena con cada mensaje que entra (3.1), no con los que salen, ni con la
 * conversación abierta y a la vista (3.2); una ráfaga, una vez cada 3 s (3.3);
 * apagado no suena (3.4). El título lleva el número (3.6).
 */
import { act, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const actions = vi.hoisted(() => ({ inboxCountsAction: vi.fn() }));
vi.mock("@/app/(console)/inbox/actions", () => actions);
const chime = vi.hoisted(() => ({ playChime: vi.fn(() => true) }));
vi.mock("../chime", async (orig) => ({ ...(await orig<typeof import("../chime")>()), playChime: chime.playChime, armChime: () => () => undefined }));

const { FakeEventSource } = await import("@/components/inbox/__tests__/view-harness");
const { withQuery } = await import("@/test/query");
const { LiveStreamProvider } = await import("../live-stream");
const { InboxAlerts } = await import("../inbox-alerts");
const { setSoundOn, resetChimeForTests } = await import("../chime");

const inbound = (id = "c1") => ({ event: "message.new", conversation_id: id, direction: "inbound" });

function mount() {
  render(
    withQuery(
      <LiveStreamProvider enabled>
        <InboxAlerts />
      </LiveStreamProvider>,
    ),
  );
  return FakeEventSource.last!;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date("2026-11-26T12:00:00Z"));
  chime.playChime.mockClear();
  actions.inboxCountsAction.mockReset().mockResolvedValue({ ok: true, data: { unread: 0, waiting: 0 } });
  vi.stubGlobal("EventSource", FakeEventSource);
  document.title = "Reservas · Auphere";
  window.history.replaceState(null, "", "/reservas");
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetChimeForTests();
  window.localStorage.clear();
});

describe("el sonido", () => {
  it("suena con un mensaje que entra, en cualquier pantalla (3.1)", () => {
    const es = mount();
    act(() => es.emit("message.new", inbound()));
    expect(chime.playChime).toHaveBeenCalledTimes(1);
  });

  it("no suena con un mensaje que sale (3.1)", () => {
    const es = mount();
    act(() => es.emit("message.new", { ...inbound(), direction: "outbound" }));
    act(() => es.emit("conversation.updated", { event: "conversation.updated", conversation_id: "c1" }));
    expect(chime.playChime).not.toHaveBeenCalled();
  });

  it("no suena si esa conversación está abierta y a la vista (3.2), sí si es otra", () => {
    window.history.replaceState(null, "", "/inbox?c=c1");
    const es = mount();
    act(() => es.emit("message.new", inbound("c1")));
    expect(chime.playChime).not.toHaveBeenCalled();
    act(() => es.emit("message.new", inbound("c2")));
    expect(chime.playChime).toHaveBeenCalledTimes(1);
  });

  it("una ráfaga suena una vez cada 3 s como mucho (3.3)", () => {
    const es = mount();
    act(() => {
      es.emit("message.new", inbound("c1"));
      es.emit("message.new", inbound("c2"));
      es.emit("message.new", inbound("c3"));
    });
    expect(chime.playChime).toHaveBeenCalledTimes(1);
    act(() => void vi.advanceTimersByTime(3100));
    act(() => es.emit("message.new", inbound("c4")));
    expect(chime.playChime).toHaveBeenCalledTimes(2);
  });

  it("apagado no suena (3.4)", () => {
    setSoundOn(false);
    const es = mount();
    act(() => es.emit("message.new", inbound()));
    expect(chime.playChime).not.toHaveBeenCalled();
  });
});

describe("el título", () => {
  it("empieza por «(N) » con mensajes sin leer, y sube con el aviso (3.6, 3.7)", async () => {
    actions.inboxCountsAction.mockResolvedValue({ ok: true, data: { unread: 2, waiting: 0 } });
    const es = mount();
    await waitFor(() => expect(document.title).toBe("(2) Reservas · Auphere"));
    actions.inboxCountsAction.mockResolvedValue({ ok: true, data: { unread: 3, waiting: 0 } });
    act(() => es.emit("message.new", inbound()));
    await act(async () => void vi.advanceTimersByTime(500));
    await waitFor(() => expect(document.title).toBe("(3) Reservas · Auphere"));
  });

  it("lo vuelve a poner cuando la navegación cambia el título", async () => {
    actions.inboxCountsAction.mockResolvedValue({ ok: true, data: { unread: 5, waiting: 0 } });
    mount();
    await waitFor(() => expect(document.title).toBe("(5) Reservas · Auphere"));
    document.title = "Bandeja · Auphere";
    await waitFor(() => expect(document.title).toBe("(5) Bandeja · Auphere"));
  });
});
