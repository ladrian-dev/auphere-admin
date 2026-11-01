import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { conversation, detail, message, page } from "./fixtures";
import { InboxViewRef, a, renderInbox, resetActions } from "./view-harness";

vi.mock("@/app/(console)/inbox/actions", async () => (await import("./view-harness")).a);
InboxViewRef.current = (await import("../inbox-view")).InboxView;

const ID = "11111111-1111-4111-8111-111111111111";
const opened = { detail: detail(), thread: { items: [message()], next_before: null } };

/** Spec 030 (R12, T074): resolve, reopen and come back to it later. */
describe("resolver, reabrir y marcar como no leída", () => {
  beforeEach(resetActions);

  it("resolving says so briefly and leaves «Reabrir» in place", async () => {
    a.resolveAction.mockResolvedValue({ ok: true, data: detail({ state: "resolved" }) });
    a.openConversationAction.mockResolvedValue({ ok: true, data: { ...opened, detail: detail({ state: "resolved" }) } });
    renderInbox({ selectedId: ID, open: opened });

    await userEvent.click(screen.getByRole("button", { name: "Marcar como resuelta" }));
    expect(await screen.findByText("Conversación resuelta")).toBeInTheDocument();
    expect(screen.getByText("Conversación resuelta").closest("[role=status]")).not.toBeNull();
    expect(screen.getByText(/Si el contacto vuelve a escribir, se reabre/)).toBeInTheDocument();

    a.reopenAction.mockResolvedValue({ ok: true, data: detail({ state: "agent" }) });
    a.openConversationAction.mockResolvedValue({ ok: true, data: opened });
    await userEvent.click(screen.getAllByRole("button", { name: "Reabrir" })[0]!);
    expect(a.reopenAction).toHaveBeenCalledWith({ id: ID });
    expect(await screen.findByRole("button", { name: "Tomar el control" })).toBeInTheDocument();
  });

  it("marking as unread closes it and counts it again", async () => {
    a.markUnreadAction.mockResolvedValue({ ok: true, data: null });
    renderInbox({ selectedId: ID, open: opened });
    await userEvent.click(screen.getByRole("button", { name: "Marcar como no leída" }));
    expect(a.markUnreadAction).toHaveBeenCalledWith({ id: ID });
    expect(await screen.findByText("Marcada como no leída")).toBeInTheDocument();
    expect(screen.getByText("Elige una conversación para verla aquí.")).toBeInTheDocument();
    expect(a.listConversationsAction).toHaveBeenCalled();
  });
});

/** Owner, 2026-11-01: clear and delete live in the «⋯» menu and always ask first. */
describe("vaciar y eliminar el chat", () => {
  beforeEach(resetActions);

  async function pick(item: string) {
    await userEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: item }));
  }

  it("clearing asks first, says the truth about what stays, and empties the thread", async () => {
    a.clearChatAction.mockResolvedValue({ ok: true, data: detail() });
    a.openConversationAction.mockResolvedValue({ ok: true, data: { ...opened, thread: { items: [], next_before: null } } });
    renderInbox({ selectedId: ID, open: opened });

    await pick("Vaciar chat");
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("¿Vaciar este chat?");
    expect(dialog).toHaveTextContent("archivados");
    expect(a.clearChatAction).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Vaciar chat" }));
    expect(a.clearChatAction).toHaveBeenCalledWith({ id: ID });
    expect(await screen.findByText("Chat vaciado")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("deleting closes the conversation and refreshes the list", async () => {
    a.archiveChatAction.mockResolvedValue({ ok: true, data: null });
    renderInbox({ selectedId: ID, open: opened });

    await pick("Eliminar chat");
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("empieza un chat nuevo");
    await userEvent.click(within(dialog).getByRole("button", { name: "Eliminar chat" }));

    expect(a.archiveChatAction).toHaveBeenCalledWith({ id: ID });
    expect(await screen.findByText("Chat eliminado")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: detail().contact.name })).toBeNull();
    expect(a.listConversationsAction).toHaveBeenCalled();
  });

  it("if it fails, the dialog stays and says so", async () => {
    a.archiveChatAction.mockResolvedValue({ ok: false, status: 500, message: "" });
    renderInbox({ selectedId: ID, open: opened });

    await pick("Eliminar chat");
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Eliminar chat" }));
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Chat eliminado")).toBeNull();
  });

  it("cancelling does nothing", async () => {
    renderInbox({ selectedId: ID, open: opened });
    await pick("Vaciar chat");
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(a.clearChatAction).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

/** Owner, 2026-11-01: a client with several channels can look at one. */
describe("el filtro por canal", () => {
  beforeEach(resetActions);

  it("does not show with a single channel", () => {
    renderInbox();
    expect(screen.queryByRole("group", { name: "Canal" })).toBeNull();
  });

  it("asks the list for that channel, and clicking it again shows all", async () => {
    const several = page([conversation()], { channel_kinds: ["instagram", "messenger", "whatsapp"] });
    a.listConversationsAction.mockResolvedValue({ ok: true, data: several });
    renderInbox({ page: several });

    const group = screen.getByRole("group", { name: "Canal" });
    const instagram = within(group).getByRole("button", { name: "Instagram" });
    expect(within(group).getByRole("button", { name: "Messenger" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Todos los canales" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(instagram);
    expect(instagram).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(a.listConversationsAction).toHaveBeenLastCalledWith(expect.objectContaining({ channel: "instagram" })));

    await userEvent.click(instagram);
    await waitFor(() => expect(a.listConversationsAction).toHaveBeenLastCalledWith(expect.objectContaining({ channel: undefined })));
  });
});
