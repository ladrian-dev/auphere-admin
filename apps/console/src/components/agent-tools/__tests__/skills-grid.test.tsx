import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { SkillsOut } from "@/lib/backend/agent-tools-types";

import { SkillsGrid } from "../skills-grid";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/skills/actions", () => ({ saveSkillsAction: vi.fn() }));

const data: SkillsOut = {
  version: 3,
  version_status: "staged",
  active_version: 2,
  has_draft: true,
  skills: [
    { name: "booking_reminders", description: "Send booking reminders", version: "1.2.0", activatable: true, enabled: true, enabled_in_active: true },
    { name: "upsell_products", description: "Suggest products", version: "0.9.0", activatable: false, enabled: false, enabled_in_active: false },
  ],
};

describe("SkillsGrid (CP-14)", () => {
  it("renders cards, disables non-activatable and enables save after a toggle", () => {
    render(
      <LocaleProvider locale="es">
        <SkillsGrid refId="demo" data={data} canWrite />
      </LocaleProvider>,
    );
    expect(screen.getByText("booking_reminders")).toBeInTheDocument();
    expect(screen.getByText("Versión 1.2.0")).toBeInTheDocument();
    expect(screen.getByText("En la versión activa")).toBeInTheDocument();
    expect(screen.getByText("1 de 2 activadas")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Guardar habilidades" });
    expect(save).toBeDisabled();
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes[1]).toHaveAttribute("aria-disabled", "true");
    expect(boxes[0]).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText(/No activable en esta versión/)).toBeInTheDocument();
    fireEvent.click(boxes[0]!);
    expect(screen.getByText("0 de 2 activadas")).toBeInTheDocument();
    expect(save).not.toBeDisabled();
  });
  it("read-only roles get a hint and no save button", () => {
    render(
      <LocaleProvider locale="en">
        <SkillsGrid refId="demo" data={data} canWrite={false} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Your role can only view skills.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save skills" })).toBeNull();
    for (const b of screen.getAllByRole("checkbox")) expect(b).toHaveAttribute("aria-disabled", "true");
  });
  it("empty catalogue shows the empty state", () => {
    render(
      <LocaleProvider locale="en">
        <SkillsGrid refId="demo" data={{ ...data, skills: [] }} canWrite />
      </LocaleProvider>,
    );
    expect(screen.getByText("No skills available")).toBeInTheDocument();
  });
});
