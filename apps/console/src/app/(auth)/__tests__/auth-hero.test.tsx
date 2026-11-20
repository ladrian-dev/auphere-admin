import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type Locale, t } from "@/i18n/messages";

import { AuthHero } from "../auth-hero";

// El líquido se prueba aparte (components/auth). Aquí basta con que haya hueco.
vi.mock("@/components/auth/liquid-backdrop-lazy", () => ({ LiquidBackdropLazy: () => <canvas data-testid="liquid" /> }));

function mount(lang: Locale) {
  return render(<AuthHero eyebrow={t(lang, "login.eyebrow")} title={t(lang, "auth.hero.title")} beta={t(lang, "shell.beta")} />);
}

describe("el panel de Entrar (spec 066, R1–R3)", () => {
  it("lleva el logo de verdad, no la palabra en mono (R3.1)", () => {
    const { container } = mount("es");
    expect(container.querySelector('[data-slot="brand-lockup"]')).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "Auphere" }).length).toBeGreaterThan(0);
    expect(container.querySelector(".font-mono")).toBeNull();
  });

  it("«Beta» es neutro: nada del ámbar de los avisos (R3.2)", () => {
    const { container } = mount("es");
    const beta = screen.getByText("Beta");
    expect(beta.className).not.toMatch(/warning/);
    expect(container.innerHTML).not.toMatch(/status-warning/);
  });

  it("habla el idioma que le piden (R3.3)", () => {
    mount("en");
    expect(screen.getByText("Partner console")).toBeInTheDocument();
    expect(screen.getByText("Your clients, always within reach.")).toBeInTheDocument();
  });

  it("el titular no compite con el h1 de la página", () => {
    mount("es");
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("el respaldo y el líquido están debajo, sin anunciarse (R2.7, R2.9)", () => {
    const { container } = mount("es");
    expect(container.querySelector(".auth-hero-bg")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByTestId("liquid")).toBeInTheDocument();
  });
});
