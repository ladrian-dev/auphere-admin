import { describe, expect, it } from "vitest";

import { t } from "@/i18n/messages";
import type { DraftChange } from "@/lib/backend/agent-draft-types";

import { conflictTitle, fieldLabels, joinList, overlap, theirFields } from "../fields";

/**
 * Spec 047 (historia 2): the API says what changed in keys; the console says
 * it in words, once each, and knows where two people touched the same thing.
 */
const es = (key: Parameters<typeof t>[1]) => t("es", key);

function change(over: Partial<DraftChange>): DraftChange {
  return { revision: 4, kind: "edit", by: "luis@demo.test", at: "2026-10-26T10:00:00Z", fields: [], ...over };
}

describe("lo que cambió, en palabras", () => {
  it("cada clave tiene su palabra; las de plataforma son «Otros ajustes», una sola vez", () => {
    expect(fieldLabels(["system_prompt", "settings.tone", "audience"], es)).toEqual(["Instrucciones", "Tono", "A quién responde"]);
    expect(fieldLabels(["policies", "runtime", "channels"], es)).toEqual(["Otros ajustes"]);
  });

  it("enumera como se habla", () => {
    expect(joinList([], "y")).toBe("");
    expect(joinList(["Tono"], "y")).toBe("Tono");
    expect(joinList(["Tono", "Horario", "Objetivo"], "y")).toBe("Tono, Horario y Objetivo");
  });

  it("sabe dónde tocaron los dos", () => {
    const changes = [change({ fields: ["settings.tone"] }), change({ revision: 5, fields: ["system_prompt", "settings.tone"] })];
    expect(theirFields(changes)).toEqual(["settings.tone", "system_prompt"]);
    expect(overlap(theirFields(changes), ["system_prompt", "settings.objective"])).toEqual(["system_prompt"]);
  });

  it("el título dice quién, o que publicó o descartó, o que alguien guardó", () => {
    expect(conflictTitle([])).toEqual({ key: "agents.draft.conflict.titleSomeone", who: [] });
    expect(conflictTitle([change({}), change({ by: "ana@demo.test" }), change({})])).toEqual({
      key: "agents.draft.conflict.title",
      who: ["luis@demo.test", "ana@demo.test"],
    });
    expect(conflictTitle([change({}), change({ kind: "publish", by: "ana@demo.test" })]).key).toBe("agents.draft.conflict.titlePublished");
    expect(conflictTitle([change({ kind: "discard" })]).key).toBe("agents.draft.conflict.titleDiscarded");
  });
});
