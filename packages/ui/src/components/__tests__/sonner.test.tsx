import { act, fireEvent, render, screen } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "../../test/axe";
import { Toaster } from "../sonner";

/**
 * Spec 047 (R47.6): los avisos se anuncian a los lectores de pantalla y llevan
 * su acción («Deshacer», «Reanudar», «Pruébalo»). Duran 6 segundos, pero no se
 * van mientras tienen el foco o el ratón encima. Son capa flotante: vidrio
 * (R47.9).
 */
async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

async function showUndo(onUndo = vi.fn()) {
  render(<Toaster theme="light" />);
  await act(async () => {
    toast("Agente pausado", { action: { label: "Deshacer", onClick: onUndo } });
  });
  await advance(50);
  return onUndo;
}

describe("Toaster", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(async () => {
    await act(async () => {
      toast.dismiss();
      vi.runOnlyPendingTimers();
    });
    vi.useRealTimers();
  });

  it("anuncia el aviso en una región viva y lleva su acción", async () => {
    const onUndo = await showUndo();
    const live = document.querySelector("section[aria-live]");
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live).toHaveTextContent("Agente pausado");
    const action = screen.getByRole("button", { name: "Deshacer" });
    fireEvent.click(action);
    expect(onUndo).toHaveBeenCalled();
  });

  it("dura 6 segundos", async () => {
    await showUndo();
    await advance(5_000);
    expect(screen.queryByText("Agente pausado")).not.toBeNull();
    await advance(1_500);
    expect(screen.queryByText("Agente pausado")).toBeNull();
  });

  it("no se va mientras tiene el foco, y se va cuando lo pierde", async () => {
    await showUndo();
    const action = screen.getByRole("button", { name: "Deshacer" });
    await act(async () => {
      action.focus();
    });
    await advance(15_000);
    expect(screen.queryByText("Agente pausado"), "se fue con el foco encima").not.toBeNull();
    await act(async () => {
      action.blur();
    });
    await advance(6_500);
    expect(screen.queryByText("Agente pausado")).toBeNull();
  });

  it("no se va mientras el ratón está encima", async () => {
    await showUndo();
    const list = document.querySelector("[data-sonner-toaster]")!;
    fireEvent.mouseEnter(list);
    fireEvent.mouseMove(list);
    await advance(15_000);
    expect(screen.queryByText("Agente pausado")).not.toBeNull();
  });

  it("es de vidrio: capa flotante", async () => {
    await showUndo();
    const item = document.querySelector("[data-sonner-toast]")!;
    expect(item.className).toMatch(/\bglass\b/);
  });

  it("pasa axe", async () => {
    await showUndo();
    vi.useRealTimers();
    expect(await axeViolations()).toEqual([]);
    vi.useFakeTimers();
  });
});
