import { describe, expect, it } from "vitest";

import { initialState, isScreenComplete, progressFor, toStoredSession, wizardReducer, type WizardState } from "../wizard/wizard-reducer";
import { PROFILE_A } from "../../domain/__tests__/fixtures";

const answered = (): WizardState => {
  let s = initialState(1000);
  s = wizardReducer(s, { type: "answer", questionId: "profile", value: "direccion" });
  s = wizardReducer(s, { type: "next" });
  s = wizardReducer(s, { type: "answer", questionId: "sector", value: "comercio_retail" });
  s = wizardReducer(s, { type: "next" });
  s = wizardReducer(s, { type: "answer", questionId: "teamSize", value: "11_50" });
  s = wizardReducer(s, { type: "next" });
  return s;
};

describe("wizard reducer", () => {
  it("empieza en la primera pantalla y no avanza sin respuesta", () => {
    const s = initialState(1000);
    expect(s.step).toBe("profile");
    expect(isScreenComplete("profile", s.answers)).toBe(false);
    expect(wizardReducer(s, { type: "next" }).step).toBe("profile");
  });

  it("atrás conserva las respuestas", () => {
    const s = answered();
    expect(s.step).toBe("customerType");
    const back = wizardReducer(s, { type: "back" });
    expect(back.step).toBe("teamSize");
    expect(back.answers.sector).toBe("comercio_retail");
    expect(wizardReducer(wizardReducer(back, { type: "back" }), { type: "back" }).step).toBe("profile");
    expect(wizardReducer(back, { type: "back" }).answers.profile).toBe("direccion");
  });

  it("cambiar una respuesta anterior conserva las posteriores", () => {
    const s = answered();
    const changed = wizardReducer(wizardReducer(wizardReducer(s, { type: "back" }), { type: "back" }), { type: "answer", questionId: "sector", value: "educacion" });
    expect(changed.answers.sector).toBe("educacion");
    expect(changed.answers.teamSize).toBe("11_50");
    expect(changed.answers.profile).toBe("direccion");
  });

  it("la selección múltiple respeta el máximo", () => {
    let s = initialState(1000);
    s = wizardReducer(s, { type: "answer", questionId: "frictions", value: ["tareas_manuales", "copiar_datos", "reporting", "documental"] });
    expect(s.answers.frictions).toHaveLength(3);
  });

  it("el progreso crece y el reinicio limpia todo", () => {
    const s = answered();
    expect(progressFor(s.step)).toBeGreaterThan(progressFor("profile"));
    const restarted = wizardReducer(s, { type: "restart", now: 2000 });
    expect(restarted.step).toBe("profile");
    expect(restarted.answers).toEqual({});
    expect(restarted.startedAt).toBe(2000);
    expect(restarted.result).toBeUndefined();
  });

  it("un fallo conserva las respuestas y se puede limpiar", () => {
    const s = answered();
    const failed = wizardReducer(s, { type: "fail", message: "boom" });
    expect(failed.error).toBe("boom");
    expect(failed.answers).toEqual(s.answers);
    expect(wizardReducer(failed, { type: "clearError" }).error).toBeNull();
  });

  it("completar → contacto → procesando → resultado; al revisar no se repite el contacto", () => {
    let s = initialState(1000);
    for (const [q, v] of Object.entries(PROFILE_A)) s = wizardReducer(s, { type: "answer", questionId: q as never, value: v as never });
    for (const step of ["sector", "teamSize", "customerType", "workLevel", "aiUsage", "dataLocation", "frictions", "goals", "urgency", "techCapacity", "investment", "lead"]) {
      s = wizardReducer(s, { type: "next" });
      expect(s.step).toBe(step);
    }
    expect(wizardReducer(s, { type: "back" }).step).toBe("investment");
    s = wizardReducer(s, { type: "submitted", delivered: false });
    expect(s.step).toBe("processing");
    expect(s.contactDecision).toBe("submitted");
    expect(s.delivered).toBe(false);
    s = wizardReducer(s, { type: "processed" });
    expect(s.step).toBe("result");
    const back = wizardReducer(s, { type: "back" });
    expect(back.step).toBe("investment");
    expect(wizardReducer(back, { type: "next" }).step).toBe("processing");
  });

  it("lo que se guarda nunca incluye resultado ni lead", () => {
    const s = answered();
    const stored = toStoredSession(s);
    expect(Object.keys(stored).sort()).toEqual(["answers", "startedAt", "step", "version"]);
  });

  it("hidrata desde una sesión guardada", () => {
    const s = wizardReducer(initialState(1), { type: "hydrate", session: { version: 1, step: "goals", answers: { profile: "otro" }, startedAt: 5 } });
    expect(s.step).toBe("goals");
    expect(s.answers.profile).toBe("otro");
    expect(s.startedAt).toBe(5);
  });
});
