import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Notification } from "@/lib/backend/onboarding";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
const actions = vi.hoisted(() => ({
  unreadCountAction: vi.fn(),
  listNotificationsAction: vi.fn(),
  markAllNotificationsReadAction: vi.fn(),
}));
vi.mock("@/app/(console)/notifications/actions", () => actions);

const { NotificationsBellMenu } = await import("../notifications-bell");

/**
 * Spec 047 (R47.3): la campana abre un desplegable con los 5 últimos avisos,
 * «Marcar todo como leído» y «Ver todas». Pinta datos: tiene sus cinco estados
 * (cargando, vacío, error, parcial e ideal).
 */
const NOW = Date.now();
function notif(i: number, over: Partial<Notification> = {}): Notification {
  return {
    id: `00000000-0000-4000-8000-00000000000${i}`,
    kind: "member.joined",
    severity: "info",
    data: { email: `persona${i}@ladrian.studio`, role: "Constructor" },
    external_client_ref: null,
    read: false,
    created_at: new Date(NOW - i * 3_600_000).toISOString(),
    ...over,
  };
}

const ok = <T,>(data: T) => ({ ok: true as const, data });
const fail = { ok: false as const, status: 502, message: "upstream" };

function Bell() {
  return (
    <LocaleProvider locale="es">
      <NotificationsBellMenu initialUnread={null} />
    </LocaleProvider>
  );
}

async function openBell() {
  const user = userEvent.setup();
  render(<Bell />);
  const trigger = await screen.findByRole("button", { name: /Notificaciones/ });
  // Como el prototipo: la campana lleva su borde a la vista (Andrés, 2026-10-28).
  expect(trigger.className).toMatch(/\bborder-border\b/);
  await user.click(trigger);
  const panel = await screen.findByRole("dialog", { name: "Notificaciones" });
  return { user, trigger, panel };
}

describe("NotificationsBellMenu", () => {
  beforeEach(() => {
    actions.unreadCountAction.mockReset().mockResolvedValue(ok({ unread: 3 }));
    actions.listNotificationsAction.mockReset();
    actions.markAllNotificationsReadAction.mockReset();
  });

  it("el botón dice cuántas hay sin leer", async () => {
    actions.listNotificationsAction.mockResolvedValue(ok({ items: [], next_cursor: null, unread: 0 }));
    render(<Bell />);
    expect(await screen.findByRole("button", { name: "Notificaciones — 3 sin leer" })).toBeInTheDocument();
  });

  it("ideal: los 5 últimos, «Marcar todo como leído» y «Ver todas»", async () => {
    actions.listNotificationsAction.mockResolvedValue(
      ok({ items: [1, 2, 3, 4, 5].map((i) => notif(i, { read: i > 3 })), next_cursor: "c", unread: 3 }),
    );
    const { panel } = await openBell();
    expect(actions.listNotificationsAction).toHaveBeenCalledWith({ limit: 5 });
    const items = await within(panel).findAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(items[0]).toHaveTextContent("persona1@ladrian.studio se ha unido al equipo como Constructor");
    // Las no leídas se distinguen también para un lector de pantalla.
    expect(within(items[0]!).getByText("Sin leer")).toBeInTheDocument();
    expect(within(items[4]!).queryByText("Sin leer")).toBeNull();
    expect(within(panel).getByRole("button", { name: "Marcar todo como leído" })).toBeEnabled();
    expect(within(panel).getByRole("link", { name: "Ver todas" })).toHaveAttribute("href", "/notifications");
  });

  it("un aviso de un cliente lleva a ese cliente", async () => {
    actions.listNotificationsAction.mockResolvedValue(
      ok({
        items: [notif(1, { kind: "client.out_of_quota", severity: "critical", external_client_ref: "flor", data: {} })],
        next_cursor: null,
        unread: 1,
      }),
    );
    const { panel } = await openBell();
    const link = await within(panel).findByRole("link", { name: /flor se ha quedado sin saldo/ });
    expect(link).toHaveAttribute("href", "/clients/flor");
  });

  it("«Marcar todo como leído» los marca y lo anuncia", async () => {
    actions.listNotificationsAction.mockResolvedValue(ok({ items: [notif(1), notif(2)], next_cursor: null, unread: 2 }));
    actions.markAllNotificationsReadAction.mockResolvedValue(ok({ marked: 2 }));
    const { user, panel } = await openBell();
    await within(panel).findAllByRole("listitem");
    await user.click(within(panel).getByRole("button", { name: "Marcar todo como leído" }));
    expect(actions.markAllNotificationsReadAction).toHaveBeenCalled();
    await waitFor(() => expect(within(panel).queryAllByText("Sin leer")).toHaveLength(0));
    expect(within(panel).getByRole("status")).toHaveTextContent("Todo leído.");
    expect(within(panel).queryByRole("button", { name: "Marcar todo como leído" })).toBeNull();
    expect(screen.getByRole("button", { name: "Notificaciones" })).toBeInTheDocument();
  });

  it("cargando: filas de esqueleto del tamaño de una fila", async () => {
    actions.listNotificationsAction.mockReturnValue(new Promise(() => {}));
    const { panel } = await openBell();
    expect(within(panel).getByRole("status", { name: "Cargando" })).toBeInTheDocument();
    expect(panel.querySelectorAll("[data-slot=skeleton]").length).toBeGreaterThanOrEqual(3);
  });

  it("vacío: lo dice y deja ir a todas", async () => {
    actions.listNotificationsAction.mockResolvedValue(ok({ items: [], next_cursor: null, unread: 0 }));
    const { panel } = await openBell();
    expect(await within(panel).findByText("Sin notificaciones")).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Marcar todo como leído" })).toBeNull();
    expect(within(panel).getByRole("link", { name: "Ver todas" })).toBeInTheDocument();
  });

  it("error: lo dice con palabras de la consola y deja reintentar", async () => {
    actions.listNotificationsAction.mockResolvedValueOnce(fail);
    actions.listNotificationsAction.mockResolvedValueOnce(ok({ items: [notif(1)], next_cursor: null, unread: 1 }));
    const { user, panel } = await openBell();
    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent("No se pudieron cargar las notificaciones.");
    expect(alert).not.toHaveTextContent("upstream");
    await user.click(within(panel).getByRole("button", { name: "Reintentar" }));
    expect(await within(panel).findAllByRole("listitem")).toHaveLength(1);
  });

  it("parcial: si «Marcar todo» falla, la lista se queda y se dice qué falló", async () => {
    actions.listNotificationsAction.mockResolvedValue(ok({ items: [notif(1), notif(2)], next_cursor: null, unread: 2 }));
    actions.markAllNotificationsReadAction.mockResolvedValue(fail);
    const { user, panel } = await openBell();
    await within(panel).findAllByRole("listitem");
    await user.click(within(panel).getByRole("button", { name: "Marcar todo como leído" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("No se pudieron marcar como leídas.");
    expect(within(panel).getAllByRole("listitem")).toHaveLength(2);
    expect(within(panel).getAllByText("Sin leer")).toHaveLength(2);
  });

  it("Escape la cierra y el foco vuelve a la campana", async () => {
    actions.listNotificationsAction.mockResolvedValue(ok({ items: [notif(1)], next_cursor: null, unread: 1 }));
    const { user, trigger } = await openBell();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(trigger).toHaveFocus();
  });

  it("pasa axe abierta", async () => {
    actions.listNotificationsAction.mockResolvedValue(ok({ items: [notif(1), notif(2, { read: true })], next_cursor: null, unread: 1 }));
    const { panel } = await openBell();
    await within(panel).findAllByRole("listitem");
    expect(await axeViolations()).toEqual([]);
  });
});
