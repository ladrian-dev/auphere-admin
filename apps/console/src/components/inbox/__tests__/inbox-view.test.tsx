import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ME, conversation, detail, message, page } from "./fixtures";
import { FakeEventSource, InboxViewRef, a, renderInbox, resetActions } from "./view-harness";

vi.mock("@/app/(console)/inbox/actions", async () => (await import("./view-harness")).a);
const reload = vi.hoisted(() => vi.fn());
vi.mock("../reload", () => ({ reloadPage: reload }));
InboxViewRef.current = (await import("../inbox-view")).InboxView;

const ID = "11111111-1111-4111-8111-111111111111";

/** Spec 030 (US5, US6): the Inbox end to end in the browser, with the API as mocks. */
describe("InboxView", () => {
  beforeEach(resetActions);

  it("opens a conversation, takes over and writes (CE-005: three clicks from the notice)", async () => {
    a.openConversationAction.mockResolvedValue({
      ok: true,
      data: { detail: detail(), thread: { items: [message({ text: "¿Tienen turno?" })], next_before: null } },
    });
    a.takeOverAction.mockResolvedValue({ ok: true, data: detail({ state: "person", assignee: ME, control_version: 4 }) });
    renderInbox();

    await userEvent.click(screen.getByRole("button", { name: /Ana Torres/ }));
    expect(await screen.findByText("¿Tienen turno?")).toBeInTheDocument();
    expect(a.openConversationAction).toHaveBeenCalledWith({ id: ID, markRead: true });
    expect(window.location.search).toBe(`?c=${ID}`);

    // From now on the API answers the conversation as it is after the take over.
    a.openConversationAction.mockResolvedValue({
      ok: true,
      data: { detail: detail({ state: "person", assignee: ME, control_version: 4 }), thread: { items: [], next_before: null } },
    });
    await userEvent.click(screen.getByRole("button", { name: "Tomar el control" }));
    expect(a.takeOverAction).toHaveBeenCalledWith({ id: ID, version: 3 });
    expect(await screen.findByRole("textbox", { name: "Escribir un mensaje" })).toBeInTheDocument();
  });

  it("a send shows at once and goes away with the reason if the API refuses it", async () => {
    a.openConversationAction.mockResolvedValue({
      ok: true,
      data: { detail: detail({ state: "person", assignee: ME }), thread: { items: [message()], next_before: null } },
    });
    let refuse!: (v: unknown) => void;
    a.sendMessageAction.mockReturnValue(new Promise((r) => (refuse = r)));
    renderInbox({ selectedId: ID, open: { detail: detail({ state: "person", assignee: ME }), thread: { items: [message()], next_before: null } } });

    await userEvent.type(screen.getByRole("textbox", { name: "Escribir un mensaje" }), "Te reservo el sábado{Enter}");
    const log = screen.getByRole("log");
    expect(await within(log).findByText("Te reservo el sábado")).toBeInTheDocument();
    expect(within(log).getByText("· Enviando…")).toBeInTheDocument();

    await act(async () => refuse({ ok: false, status: 409, message: "", code: "window_closed" }));
    await waitFor(() => expect(within(log).queryByText("Te reservo el sábado")).toBeNull());
    expect(screen.getByRole("alert")).toHaveTextContent("Pasaron más de 24 horas");
    expect(screen.getByRole("textbox", { name: "Escribir un mensaje" })).toHaveValue("Te reservo el sábado");
  });

  it("someone else moved it first: the real state shows, and the screen says so (412)", async () => {
    const now = detail({ state: "person", assignee: { kind: "member", name: "Luis", is_me: false }, control_version: 5 });
    a.takeOverAction.mockResolvedValue({ ok: false, status: 412, message: "", info: { error: "version_mismatch", conversation: now } });
    a.openConversationAction.mockResolvedValue({ ok: true, data: { detail: now, thread: { items: [], next_before: null } } });
    renderInbox({ selectedId: ID, open: { detail: detail(), thread: { items: [], next_before: null } } });

    await userEvent.click(screen.getByRole("button", { name: "Tomar el control" }));
    expect(await screen.findByText(/Alguien cambió esta conversación/)).toBeInTheDocument();
    expect(screen.getByText("Luis está atendiendo esta conversación.")).toBeInTheDocument();
  });

  it("says «Reconectando…» while the live line is down, and re-reads what an event names", async () => {
    a.openConversationAction.mockResolvedValue({ ok: true, data: { detail: detail(), thread: { items: [message({ text: "nuevo" })], next_before: null } } });
    renderInbox({ selectedId: ID, open: { detail: detail(), thread: { items: [], next_before: null } } });
    const es = FakeEventSource.last!;
    expect(es.url).toBe("/api/lite/inbox/stream");

    act(() => es.onerror?.());
    expect(screen.getByText("Reconectando…")).toBeInTheDocument();
    act(() => es.onopen?.());
    expect(screen.queryByText("Reconectando…")).toBeNull();

    a.listConversationsAction.mockClear();
    act(() => es.emit("message.new", { event: "message.new", conversation_id: ID, direction: "inbound" }));
    await waitFor(() => expect(a.listConversationsAction).toHaveBeenCalled(), { timeout: 2000 });
    expect(await screen.findByText("nuevo", {}, { timeout: 2000 })).toBeInTheDocument();
  });

  it("a session that expired (or an Inbox taken away) sends the person where the guard says", async () => {
    reload.mockClear();
    a.openConversationAction.mockResolvedValue({ ok: false, status: 403, message: "forbidden" });
    renderInbox();
    await userEvent.click(screen.getByRole("button", { name: /Ana Torres/ }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it("a live line that drops checks the session instead of «reconnecting» forever", async () => {
    reload.mockClear();
    a.inboxCountsAction.mockResolvedValue({ ok: false, status: 401, message: "Not signed in" });
    renderInbox();
    act(() => FakeEventSource.last!.onerror?.());
    await waitFor(() => expect(a.inboxCountsAction).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    // A second error while still down does not ask again.
    act(() => FakeEventSource.last!.onerror?.());
    expect(a.inboxCountsAction).toHaveBeenCalledTimes(1);
  });

  it("an empty inbox and a failed first read are different screens", () => {
    renderInbox({ page: page([], { has_any: false }) });
    expect(screen.getByText("Aún no hay conversaciones")).toBeInTheDocument();
  });

  it("a failed first read says so", () => {
    renderInbox({ page: null });
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos cargar la bandeja");
  });

  it("a conversation that cannot be opened offers to retry", async () => {
    renderInbox({ selectedId: ID, open: null, page: page([conversation()]) });
    expect(screen.getByText("No pudimos abrir esta conversación. Inténtalo de nuevo.")).toBeInTheDocument();
    a.openConversationAction.mockResolvedValue({ ok: true, data: { detail: detail(), thread: { items: [], next_before: null } } });
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("button", { name: "Tomar el control" })).toBeInTheDocument();
  });
});
