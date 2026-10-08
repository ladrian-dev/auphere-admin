import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { detail, message } from "./fixtures";
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
