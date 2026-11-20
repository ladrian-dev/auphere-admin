import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type Locale, t } from "@/i18n/messages";

import { AuthHero } from "../auth-hero";

// El líquido se prueba aparte (components/auth). Aquí basta con que haya hueco.
const nav = vi.hoisted(() => ({ path: "/login" }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.path }));
vi.mock("@/components/auth/liquid-backdrop-lazy", () => ({ LiquidBackdropLazy: () => <canvas data-testid="liquid" /> }));

function mount(lang: Locale) {
  return render(
    <AuthHero
      beta={t(lang, "shell.beta")}
      base={{ eyebrow: t(lang, "login.eyebrow"), title: t(lang, "auth.hero.title") }}
      signup={{
        eyebrow: t(lang, "login.eyebrow"),
        title: t(lang, "signup.hero.title"),
        body: t(lang, "signup.hero.body"),
        currentLabel: t(lang, "signup.step.current"),
        nextLabel: t(lang, "signup.step.next"),
        steps: [
          { title: t(lang, "signup.step1.title"), body: t(lang, "signup.step1.body") },
          { title: t(lang, "signup.step2.title"), body: t(lang, "signup.step2.body") },
          { title: t(lang, "signup.step3.title"), body: t(lang, "signup.step3.body") },
        ],
      }}
    />,
  );
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

  it("en el alta enseña los tres pasos del arranque, con el primero como actual (spec 067, R1)", () => {
    nav.path = "/signup/tok_abcdefghijklmnop";
    mount("es");
    expect(screen.getByText("Empieza con Auphere.")).toBeInTheDocument();
    const steps = screen.getAllByRole("listitem");
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveAttribute("aria-current", "step");
    expect(steps[1]).not.toHaveAttribute("aria-current");
    expect(steps[0]).toHaveTextContent("Crea tu cuenta");
    expect(steps[2]).toHaveTextContent("Configura tu agente y publícalo");
    nav.path = "/login";
  });

  it("fuera del alta no hay pasos (spec 067, R1.3)", () => {
    nav.path = "/forgot";
    mount("es");
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.getByText("Tus clientes, siempre al alcance.")).toBeInTheDocument();
    nav.path = "/login";
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
