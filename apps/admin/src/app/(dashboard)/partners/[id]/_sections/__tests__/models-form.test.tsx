import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";
import type { PartnerModelItemOut } from "@/lib/backend";

const h = vi.hoisted(() => ({ save: vi.fn(), success: vi.fn(), error: vi.fn(), refresh: vi.fn() }));
vi.mock("../../../actions", () => ({ setPartnerModels: (...a: unknown[]) => h.save(...a) }));
vi.mock("sonner", () => ({ toast: { success: h.success, error: h.error } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { AllowlistForm } = await import("../models-form");

/**
 * Spec 065 (T075; requisitos 8.2 y 1.3) — Partner › Configuración, la lista de
 * modelos del partner: los seis que se pueden ofrecer, también los que aún no
 * están habilitados para responder en este entorno, que lo dicen (el partner no
 * los ve hasta que se habiliten).
 */

const SIX: PartnerModelItemOut[] = [
  { model_id: "openai/gpt-5.6-sol", display_name: "Sol", allowed: true },
  { model_id: "anthropic/claude-opus-5-5", display_name: "Claude Opus 5.5", allowed: true },
  { model_id: "openai/gpt-5.6-terra", display_name: "Terra", allowed: true },
  { model_id: "anthropic/claude-sonnet-5-5", display_name: "Claude Sonnet 5.5", allowed: false },
  { model_id: "openai/gpt-5.6-luna", display_name: "Luna", allowed: true },
  { model_id: "anthropic/claude-haiku-5-5", display_name: "Claude Haiku 5.5", allowed: true },
];
const ENABLED = ["openai/gpt-5.6-sol", "openai/gpt-5.6-terra", "openai/gpt-5.6-luna"];
const NOT_YET = "Sin habilitar para responder en este entorno: el partner no lo ve hasta que se habilite.";

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

const itemOf = (name: string) => screen.getByRole("checkbox", { name }).closest("li") as HTMLElement;

describe("la lista de modelos del partner (spec 065)", () => {
  it("enseña los seis, y los que aún no responden aquí lo dicen; pasa axe", async () => {
    const { container } = render(<AllowlistForm partnerId="p1" items={SIX} enabled={ENABLED} />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(6);
    for (const name of ["Claude Opus 5.5", "Claude Sonnet 5.5", "Claude Haiku 5.5"]) {
      expect(within(itemOf(name)).getByText(NOT_YET)).toBeTruthy();
    }
    for (const name of ["Sol", "Terra", "Luna"]) {
      expect(within(itemOf(name)).queryByText(NOT_YET)).toBeNull();
    }
    expect(within(itemOf("Claude Haiku 5.5")).getByText("anthropic/claude-haiku-5-5")).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("si no se sabe qué está habilitado, no dice nada de eso", () => {
    render(<AllowlistForm partnerId="p1" items={SIX} enabled={null} />);
    expect(screen.queryByText(NOT_YET)).toBeNull();
  });

  it("vacía: lo dice", () => {
    render(<AllowlistForm partnerId="p1" items={[]} enabled={ENABLED} />);
    expect(screen.getByText("No hay modelos que se puedan ofrecer a los partners en este entorno.")).toBeTruthy();
  });

  it("quitar uno guarda la lista sin él, también si aún no responde aquí", async () => {
    h.save.mockResolvedValue({ ok: true, data: null });
    render(<AllowlistForm partnerId="p1" items={SIX} enabled={ENABLED} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Claude Haiku 5.5" }));
    expect(h.save).toHaveBeenCalledWith("p1", [
      "openai/gpt-5.6-sol",
      "anthropic/claude-opus-5-5",
      "openai/gpt-5.6-terra",
      "openai/gpt-5.6-luna",
    ]);
    await waitFor(() => expect(h.refresh).toHaveBeenCalled());
  });

  it("un nombre larguísimo se parte sin desbordar", () => {
    const long = "Donaudampfschifffahrtsgesellschaftsmodell-Großversion-5.5";
    render(<AllowlistForm partnerId="p1" items={[{ model_id: "x/long", display_name: long, allowed: true }]} enabled={null} />);
    const name = screen.getByText(long);
    expect(name.className).toMatch(/break-words|wrap-anywhere/);
    expect(name.parentElement?.className).toMatch(/min-w-0/);
  });
});
