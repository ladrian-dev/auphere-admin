import { describe, expect, it } from "vitest";

import type { AgentBundle, AgentVersion } from "@/lib/backend";

import { changedScreens, isCurrentDraft } from "../agent-history";

/**
 * Spec 017 · R3.6: el historial del agente decía cuándo pasó algo y nunca
 * qué. La entrada del borrador pendiente dice en qué pantallas difiere,
 * para no tener que abrirla a averiguarlo.
 */
const version = (n: number, status: string): AgentVersion =>
  ({
    version: n,
    status,
    system_prompt: "x",
    tools: [],
    seed_template_ref: null,
    created_by: "console:marta@example.com",
    created_at: "2026-09-26T10:00:00Z",
    promoted_at: null,
    promoted_by: null,
  }) as AgentVersion;

const bundle = (over: Partial<AgentBundle> = {}): AgentBundle => ({
  active_version: 1,
  versions: [version(2, "staged"), version(1, "active")],
  draft_screens: ["settings", "capabilities"],
  ...over,
});

describe("el historial del agente", () => {
  it("la entrada del borrador dice qué pantallas cambia", () => {
    const b = bundle();
    expect(changedScreens(version(2, "staged"), b)).toEqual(["settings", "capabilities"]);
  });

  it("la versión que atiende no lleva resumen: no hay nada pendiente en ella", () => {
    expect(changedScreens(version(1, "active"), bundle())).toEqual([]);
  });

  it("una versión preparada y luego superada ya no es el borrador", () => {
    const b = bundle({ versions: [version(3, "staged"), version(2, "staged"), version(1, "active")] });
    expect(isCurrentDraft(version(3, "staged"), b)).toBe(true);
    expect(isCurrentDraft(version(2, "staged"), b)).toBe(false);
    expect(changedScreens(version(2, "staged"), b)).toEqual([]);
  });

  it("sin versión activa, el primer borrador sigue siendo el borrador", () => {
    const b = bundle({ active_version: null, versions: [version(1, "staged")], draft_screens: ["prompt"] });
    expect(changedScreens(version(1, "staged"), b)).toEqual(["prompt"]);
  });

  it("una versión antigua por debajo de la activa no es un borrador pendiente", () => {
    const b = bundle({ active_version: 3, versions: [version(3, "active"), version(2, "staged")] });
    expect(isCurrentDraft(version(2, "staged"), b)).toBe(false);
  });
});
