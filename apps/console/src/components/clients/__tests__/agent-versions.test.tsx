import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { AgentBundle, AgentVersion } from "@/lib/backend";

import { AgentVersions } from "../agent-versions";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/actions", () => ({
  publishAgentAction: vi.fn(),
  rollbackAgentAction: vi.fn(),
  stageAgentAction: vi.fn(),
}));

const version = (n: number, status: AgentVersion["status"]): AgentVersion => ({
  version: n,
  status,
  system_prompt: `prompt ${n}`,
  tools: [],
  seed_template_ref: null,
  created_by: null,
  created_at: "2026-10-01T10:00:00Z",
  promoted_at: null,
  promoted_by: null,
});

function pintar(bundle: AgentBundle) {
  return render(
    <LocaleProvider locale="es">
      <AgentVersions refId="flor" bundle={bundle} canWrite />
    </LocaleProvider>,
  );
}

describe("Versiones del agente · regla de los tres puntos (2026-10-02)", () => {
  it("con más de dos botones en la lista, cada versión los pliega en «⋯»", async () => {
    pintar({ active_version: 3, versions: [version(3, "active"), version(2, "staged"), version(1, "archived")], draft_screens: [] });
    expect(screen.queryByRole("button", { name: "Publicar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Revertir a esta" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Opciones de la versión 2" }));
    expect(await screen.findByRole("menuitem", { name: "Publicar" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Ver prompt" })).toBeTruthy();
  });

  it("el número de versión abre y cierra el prompt en un clic", async () => {
    pintar({ active_version: 3, versions: [version(3, "active"), version(2, "staged"), version(1, "archived")], draft_screens: [] });
    await userEvent.click(screen.getByRole("button", { name: "v1" }));
    expect(screen.getByText("prompt 1")).toBeTruthy();
  });

  it("con dos botones o menos, se quedan a la vista", () => {
    pintar({ active_version: 1, versions: [version(1, "active")], draft_screens: [] });
    expect(screen.getByRole("button", { name: "Ver prompt" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Opciones de la versión/ })).toBeNull();
  });
});
