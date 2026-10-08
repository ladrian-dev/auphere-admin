import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

const push = vi.fn();
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/components/shell/lite-notifications-actions", () => ({
  liteUnreadCountAction: vi.fn(async () => ({ ok: true, data: { unread: 1 } })),
  liteListNotificationsAction: vi.fn(async () => ({
    ok: true,
    data: {
      items: [
        {
          id: "n-1",
          kind: "inbox.waiting",
          severity: "warning",
          data: { conversation_id: "11111111-1111-4111-8111-111111111111", contact: "Ana Torres" },
          read: false,
          created_at: "2026-10-08T11:00:00Z",
          external_client_ref: null,
        },
      ],
      unread: 1,
    },
  })),
  liteMarkNotificationReadAction: vi.fn(async () => ({ ok: true, data: {} })),
  liteReadAllNotificationsAction: vi.fn(async () => ({ ok: true, data: { marked: 1 } })),
}));

const { LiteNotificationsBell } = await import("@/components/shell/lite-notifications-bell");
const { Composer } = await import("../composer");

/** Spec 030 (R11, R15, T069): nobody learns late that the agent asked for help. */
describe("lo que espera a una persona", () => {
  it("the composer says it is waiting, why, and offers to take over", async () => {
    const onTakeOver = vi.fn();
    render(
      <LocaleProvider locale="es">
        <Composer
          mode={{ kind: "waiting", reason: "Pide un reembolso de una compra" }}
          busy={false}
          sendError={null}
          replies={[]}
          repliesApi={{ create: vi.fn(), edit: vi.fn(), archive: vi.fn() }}
          attaching={null}
          onTakeOver={onTakeOver}
          onGiveBack={vi.fn()}
          onReopen={vi.fn()}
          onSend={vi.fn()}
          onAttach={vi.fn()}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText("Esta conversación espera a una persona")).toBeInTheDocument();
    expect(screen.getByText("Pide un reembolso de una compra")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Tomar el control" }));
    expect(onTakeOver).toHaveBeenCalled();
  });

  it("the bell's notice opens that conversation (CE-005: bell → notice → «Tomar el control»)", async () => {
    render(
      <LocaleProvider locale="es">
        <LiteNotificationsBell modules={["panel", "inbox"]} />
      </LocaleProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: /Notificaciones/ }));
    await userEvent.click(await screen.findByText(/Ana Torres/));
    expect(push).toHaveBeenCalledWith("/inbox?c=11111111-1111-4111-8111-111111111111");
  });
});
