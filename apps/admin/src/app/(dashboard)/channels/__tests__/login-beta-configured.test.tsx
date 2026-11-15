import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  countries: vi.fn(),
  catalog: vi.fn(),
  channels: vi.fn(),
}));
vi.mock("@/lib/backend-whatsapp-beta", () => ({ loginBetaBackend: { countries: () => h.countries() } }));
vi.mock("@/lib/backend", () => ({
  backend: { getChannelCatalog: () => h.catalog(), listAllChannels: () => h.channels() },
}));
vi.mock("@/lib/session", () => ({ requireOperator: async () => ({ id: "op-1" }) }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound");
  },
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock("../whatsapp-login/actions", () => ({ setLoginBetaCountryAction: vi.fn() }));
vi.mock("../whatsapp-login/countries", async (real) => ({
  ...(await real<typeof import("../whatsapp-login/countries")>()),
  countryNames: () => undefined,
}));

const { ChannelsTabs } = await import("../channels-tabs");
const { default: ChannelsPage } = await import("../page");
const { default: WhatsappLoginBetaPage } = await import("../whatsapp-login/page");

const BETA = "Beta «WhatsApp login»";
const CHILE = { country: "CL", enabled_at: "2026-10-20T10:00:00Z", enabled_by: "operator:op-1" };

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
  h.catalog.mockResolvedValue([]);
  h.channels.mockResolvedValue({ channels: [], unreadable: [] });
});

/** Spec 059 (5.3, T035): without Meta's configuration for signing up without an account, no beta. */
describe("the «WhatsApp login» beta only exists where it is configured", () => {
  it("the tabs offer it only when the deployment has the configuration", () => {
    const { unmount } = render(<ChannelsTabs current="/channels" beta={false} />);
    expect(screen.getByRole("link", { name: "Canales de los clientes" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: BETA })).toBeNull();
    unmount();
    render(<ChannelsTabs current="/channels" beta />);
    expect(screen.getByRole("link", { name: BETA }).getAttribute("href")).toBe("/channels/whatsapp-login");
  });

  it("Canales hides the tab when the beta is not configured, or cannot be read", async () => {
    h.countries.mockResolvedValue({ configured: false, countries: [] });
    const { unmount } = render(await ChannelsPage());
    expect(screen.queryByRole("link", { name: BETA })).toBeNull();
    unmount();

    h.countries.mockRejectedValue(new Error("down"));
    const second = render(await ChannelsPage());
    expect(screen.queryByRole("link", { name: BETA })).toBeNull();
    second.unmount();

    h.countries.mockResolvedValue({ configured: true, countries: [] });
    render(await ChannelsPage());
    expect(screen.getByRole("link", { name: BETA })).toBeTruthy();
  });

  it("its page does not exist without the configuration", async () => {
    h.countries.mockResolvedValue({ configured: false, countries: [CHILE] });
    await expect(WhatsappLoginBetaPage()).rejects.toThrow("notFound");
  });

  it("its page shows the countries when configured, and says so when it cannot read them", async () => {
    h.countries.mockResolvedValue({ configured: true, countries: [CHILE] });
    const { unmount } = render(await WhatsappLoginBetaPage());
    expect(screen.getByRole("region", { name: "Activada en" })).toBeTruthy();
    expect(screen.getByRole("link", { name: BETA }).getAttribute("aria-current")).toBe("page");
    unmount();

    h.countries.mockRejectedValue(new Error("down"));
    render(await WhatsappLoginBetaPage());
    expect(screen.getByText("No se pudo leer la beta por país")).toBeTruthy();
  });
});
