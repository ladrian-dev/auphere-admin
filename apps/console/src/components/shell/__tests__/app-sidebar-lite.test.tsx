import { act, cleanup, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SidebarProvider } from "@nexus/ui";

import { LocaleProvider } from "@/i18n/client";
import { PARTNER_MODULES } from "@/lib/principal-access";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/lib/auth-actions", () => ({ signOutAction: vi.fn() }));
const counts = vi.hoisted(() => ({ unread: 0 }));
vi.mock("@/app/(console)/inbox/actions", () => ({
  inboxCountsAction: vi.fn(async () => ({ ok: true, data: { unread: counts.unread, waiting: 0 } })),
}));

const { AppSidebar } = await import("../app-sidebar");

/**
 * Spec 030 (R3.1, R3.2, R3.3): el lateral de una persona de cliente lleva al
 * pie su nombre y el de su negocio, y nada del partner. Spec 045 (R7): junto
 * al logotipo, la misma insignia «Beta» que el partner, con su propia pista;
 * «lite» (jerga interna) ya no se ve.
 */
function renderSidebar(props: Parameters<typeof AppSidebar>[0], open = true) {
  return render(
    <LocaleProvider locale="es">
      <SidebarProvider defaultOpen={open}>
        <AppSidebar {...props} />
      </SidebarProvider>
    </LocaleProvider>,
  );
}

const CLIENT_HINT = "Auphere Customers está en fase beta. Si algo no funciona como esperas, cuéntaselo a quien te dio acceso.";

describe("AppSidebar — consola lite", () => {
  const user = { name: "Valeria Ríos", email: "valeria@minegocio.test" };

  it("shows the client's modules and the business at the foot", () => {
    renderSidebar({
      who: { kind: "client", modules: ["panel", "inbox", "usage"], clientName: "Flor y Encanto" },
      partnerName: "Amacrux",
      partnerSlug: "amacrux",
      user,
    });
    const nav = screen.getByLabelText("Primary");
    const links = within(nav).getAllByRole("link").map((a) => a.textContent);
    expect(links).toEqual(["Panel", "Bandeja de entrada", "Consumo"]);
    expect(screen.getByText("Flor y Encanto")).toBeTruthy();
    expect(screen.queryByText("Clientes")).toBeNull();
    expect(screen.queryByText("Auditoría")).toBeNull();
  });

  it("says how many conversations are unread next to the inbox (R3.5)", async () => {
    counts.unread = 3;
    renderSidebar({
      who: { kind: "client", modules: ["panel", "inbox", "usage"], clientName: "Flor y Encanto" },
      partnerName: "Amacrux",
      partnerSlug: "amacrux",
      user,
    });
    const inbox = screen.getByRole("link", { name: /Bandeja de entrada/ });
    expect(await within(inbox).findByText("3")).toBeTruthy();
    expect(within(inbox).getByText("3 sin leer")).toBeTruthy();
    // The open Inbox announces fresher counts and the badge follows at once.
    act(() => {
      window.dispatchEvent(new CustomEvent("nexus:inbox-counts", { detail: { unread: 5, waiting: 0 } }));
    });
    expect(within(inbox).getByText("5")).toBeTruthy();
    counts.unread = 0;
  });

  it("says Beta like the partner's, with the client's own hint, and never «lite» (spec 045, R7.1–R7.2)", () => {
    renderSidebar({
      who: { kind: "client", modules: ["panel", "inbox", "usage"], clientName: "Flor y Encanto" },
      partnerName: "Amacrux",
      partnerSlug: "amacrux",
      user,
    });
    const beta = screen.getByText("Beta");
    expect(beta.getAttribute("title")).toBe(CLIENT_HINT);
    expect(screen.queryByText("lite")).toBeNull();

    cleanup();
    renderSidebar({
      who: { kind: "partner", role: "owner", modules: [...PARTNER_MODULES] },
      partnerName: "Amacrux",
      partnerSlug: "amacrux",
      user,
    });
    const partnerBeta = screen.getByText("Beta");
    // The same component and tone: only the hint is the client's own.
    expect(partnerBeta.className).toBe(beta.className);
    expect(partnerBeta.getAttribute("title")).not.toBe(CLIENT_HINT);
  });

  it("hides the badge like the partner's when the sidebar is folded (spec 045, story 3)", () => {
    renderSidebar(
      {
        who: { kind: "client", modules: ["panel", "inbox", "usage"], clientName: "Flor y Encanto" },
        partnerName: "Amacrux",
        partnerSlug: "amacrux",
        user,
      },
      false,
    );
    expect(screen.getByText("Beta")).toHaveClass("opacity-0");
  });

  it("keeps the partner sidebar its own", () => {
    renderSidebar({
      who: { kind: "partner", role: "owner", modules: [...PARTNER_MODULES] },
      partnerName: "Amacrux",
      partnerSlug: "amacrux",
      user,
    });
    expect(screen.queryByText("lite")).toBeNull();
    expect(screen.getByText("Beta").getAttribute("title")).toMatch(/^La consola está en fase beta/);
    expect(screen.getByText("Clientes")).toBeTruthy();
  });
});
