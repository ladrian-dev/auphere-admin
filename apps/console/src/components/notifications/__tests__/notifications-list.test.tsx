import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/notifications" }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
const actions = vi.hoisted(() => ({
  listNotificationsAction: vi.fn(),
  markAllNotificationsReadAction: vi.fn(),
  markNotificationReadAction: vi.fn(),
}));
vi.mock("@/app/(console)/notifications/actions", () => actions);
vi.mock("@/app/(console)/usage/money-actions", () => ({}));

import { LocaleProvider } from "@/i18n/client";
import type { Notification, NotificationPage } from "@/lib/backend/onboarding";

const { NotificationsList } = await import("../notifications-list");

/**
 * Spec 047 — Notificaciones como el prototipo «Consola de partners v2»: la
 * cabecera de la página lleva «Marcar todas como leídas» solo si hay sin leer,
 * el filtro es el conmutador de vidrio y la lista va en una tarjeta, con el
 * punto de sin leer, la insignia con su icono, la hora relativa, «Ver cliente»
 * y «Marcar como leída»; las leídas, atenuadas.
 */
const note = (over: Partial<Notification> = {}): Notification => ({
  id: "n1",
  kind: "unknown.kind",
  severity: "warning",
  data: {},
  external_client_ref: "flor",
  read: false,
  created_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
  ...over,
});
const page = (items: Notification[], unread: number): NotificationPage => ({ items, next_cursor: null, unread });
const wrap = (p: NotificationPage) =>
  render(
    <LocaleProvider locale="es">
      <main>
        <NotificationsList initial={p} initialFilter="all" clientNames={{ flor: "Flor y Encanto" }} />
      </main>
    </LocaleProvider>,
  );

describe("Notificaciones · como el prototipo", () => {
  beforeEach(() => vi.clearAllMocks());

  it("cabecera con «Marcar todas como leídas» solo si hay sin leer", () => {
    const { unmount } = wrap(page([note()], 1));
    expect(screen.getByRole("heading", { level: 1, name: "Notificaciones" })).toBeInTheDocument();
    const header = screen.getByRole("heading", { level: 1 }).closest("header")!;
    expect(within(header).getByRole("button", { name: "Marcar todas como leídas" })).toBeInTheDocument();
    unmount();
    wrap(page([note({ read: true })], 0));
    expect(screen.queryByRole("button", { name: "Marcar todas como leídas" })).toBeNull();
  });

  it("el filtro es el conmutador de vidrio con el recuento de sin leer", async () => {
    const user = userEvent.setup();
    actions.listNotificationsAction.mockResolvedValue({ ok: true, data: page([], 0) });
    wrap(page([note()], 3));
    const filter = screen.getByRole("radiogroup", { name: "Qué notificaciones se ven" });
    expect(filter).toHaveAttribute("data-slot", "segmented-control");
    expect(within(filter).getByRole("radio", { name: "Todas" })).toHaveAttribute("aria-checked", "true");
    await user.click(within(filter).getByRole("radio", { name: "Sin leer (3)" }));
    await waitFor(() => expect(actions.listNotificationsAction).toHaveBeenCalledWith({ unread: true, limit: 20 }));
  });

  it("cada aviso: punto de sin leer, insignia, hora relativa, «Ver cliente» y «Marcar como leída»", async () => {
    const { container } = wrap(page([note(), note({ id: "n2", read: true, severity: "info", external_client_ref: null })], 1));
    const list = screen.getByRole("list");
    expect(list.closest("[data-slot=notifications-card]")).not.toBeNull();
    const [unread, read] = within(list).getAllByRole("listitem");
    expect(within(unread!).getByLabelText("Sin leer")).toBeInTheDocument();
    expect(within(unread!).getByText("Aviso")).toBeInTheDocument();
    expect(within(unread!).getByText("hace 2 horas")).toBeInTheDocument();
    expect(within(unread!).getByText("Ver cliente").closest("a")).toHaveAttribute("href", "/clients/flor");
    expect(within(unread!).getByRole("button", { name: "Marcar como leída" })).toBeInTheDocument();
    expect(read!.className).toMatch(/opacity-75/);
    expect(within(read!).queryByRole("button", { name: "Marcar como leída" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });
});
