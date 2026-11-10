import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { axeViolations } from "../../test/axe";
import { AGENT_STATE_TONE, CHANNEL_STATE_TONE, StatusBadge } from "../status-badge";

/**
 * Spec 047 (`contracts/events.md` §1): el estado visible del agente y del
 * canal se pinta con su tono, y la tabla de tonos es una sola, la del contrato.
 * La API manda el código; la consola, la lite y la app ponen el texto.
 */
describe("StatusBadge · los tonos del contrato", () => {
  it("el estado visible del agente (§1.3)", () => {
    expect(AGENT_STATE_TONE).toEqual({
      archived: "muted",
      paused: "warn",
      draft: "muted",
      serving: "positive",
      testing: "info",
      ready_no_channel: "info",
    });
  });

  it("el estado visible del canal (§1.2)", () => {
    expect(CHANNEL_STATE_TONE).toEqual({
      pending_link: "info",
      disconnected: "muted",
      problem: "danger",
      paused: "warn",
      unconfigured: "muted",
      team_only: "info",
      everyone: "positive",
    });
  });

  it.each(["positive", "info", "warn", "danger", "muted"] as const)("pinta el tono %s del contrato", (tone) => {
    render(<StatusBadge tone={tone}>Estado</StatusBadge>);
    const badge = screen.getByText("Estado").closest("[data-slot=status-badge]")!;
    expect(badge).toHaveAttribute("data-tone", tone);
    // `warn` es el nombre del contrato para el ámbar del sistema: mismo color que `warning`.
    const dot = badge.querySelector("[data-slot=status-dot]");
    expect(dot).toHaveAttribute("data-tone", tone === "warn" ? "warning" : tone);
  });

  it.each([
    ["positive", "text-status-positive-text"],
    ["warn", "text-status-warning-text"],
    ["danger", "text-status-danger-text"],
    ["info", "text-status-info-text"],
  ] as const)("como el prototipo, el texto del tono %s va en su color legible", (tone, cls) => {
    render(<StatusBadge tone={tone}>Estado</StatusBadge>);
    expect(screen.getByText("Estado").closest("[data-slot=status-badge]")).toHaveClass(cls);
  });

  it("con un icono, el icono va en línea con el texto y sustituye al punto (como el prototipo)", () => {
    render(
      <StatusBadge tone="info">
        <svg data-testid="icono" aria-hidden="true" />
        Leído de la web · revísalo
      </StatusBadge>,
    );
    const badge = screen.getByText(/Leído de la web/).closest("[data-slot=status-badge]")!;
    const inner = screen.getByTestId("icono").parentElement!;
    expect(inner.className).toMatch(/\binline-flex\b/);
    expect(inner.className).toMatch(/items-center/);
    expect(badge.className).toContain("[&:has(svg)>[data-slot=status-dot]]:hidden");
  });

  it("un estado nombra su texto: el punto es decorativo y no se lee dos veces", async () => {
    render(<StatusBadge tone={AGENT_STATE_TONE.serving}>Atendiendo</StatusBadge>);
    expect(screen.getByText("Atendiendo")).toBeVisible();
    expect(await axeViolations()).toEqual([]);
  });
});
