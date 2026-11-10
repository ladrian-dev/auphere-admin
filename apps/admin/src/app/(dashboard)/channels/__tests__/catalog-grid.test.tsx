import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ChannelCatalogEntry } from "@/lib/backend";

import { CatalogGrid } from "../catalog-grid";

const CATALOG: ChannelCatalogEntry[] = [
  { key: "whatsapp", name: "WhatsApp", description: "d", availability: "available", note: null },
  { key: "tiktok", name: "TikTok", description: "d", availability: "pending", note: "Pendiente de la aprobación de TikTok." },
  { key: "instagram", name: "Instagram", description: "d", availability: "coming_soon", note: "Diseñado (ADR-030); se construye en su propia spec." },
  { key: "telegram", name: "Telegram", description: "d", availability: "coming_soon", note: null },
];

/** Spec 047 (T172, 54.8): «Pendiente» and «Próximamente» are seen here, with why. */
describe("the channel catalog of the panel", () => {
  it("says how many numbers use what works", () => {
    render(<CatalogGrid catalog={CATALOG} active={{ whatsapp: 12 }} />);
    const whatsapp = screen.getByText("WhatsApp").closest("li")!;
    expect(within(whatsapp).getByText("12 activos")).toBeTruthy();
    expect(whatsapp.getAttribute("aria-disabled")).toBeNull();
  });

  it("shows what is pending or coming soon, with its reason, and that it cannot start", () => {
    render(<CatalogGrid catalog={CATALOG} active={{}} />);
    const tiktok = screen.getByText("TikTok").closest("li")!;
    expect(within(tiktok).getByText("Pendiente")).toBeTruthy();
    expect(within(tiktok).getByText("Pendiente de la aprobación de TikTok.")).toBeTruthy();
    expect(tiktok.getAttribute("aria-disabled")).toBe("true");
    const instagram = screen.getByText("Instagram").closest("li")!;
    expect(within(instagram).getByText("Próximamente")).toBeTruthy();
    expect(within(instagram).getByText(/ADR-030/)).toBeTruthy();
    expect(within(instagram).queryByText(/activos/)).toBeNull();
    expect(screen.getAllByText("Próximamente")).toHaveLength(2);
  });
});
