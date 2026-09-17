import { afterEach, describe, expect, it, vi } from "vitest";

import { SESSION_KEY, clearSession, loadSession, saveSession } from "../storage";

const session = { version: 1 as const, step: "goals" as const, answers: { profile: "direccion" as const, frictions: ["tareas_manuales" as const] }, startedAt: 10 };

afterEach(() => {
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("storage de sesión", () => {
  it("guarda y restaura", () => {
    saveSession(session);
    expect(loadSession()).toEqual({ status: "restored", session });
  });

  it("vacío cuando no hay nada", () => {
    expect(loadSession()).toEqual({ status: "empty" });
  });

  it("descarta JSON corrupto y limpia", () => {
    window.sessionStorage.setItem(SESSION_KEY, "{");
    expect(loadSession()).toEqual({ status: "discarded" });
    expect(window.sessionStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it("descarta otra versión o campos desconocidos", () => {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ ...session, version: 2 }));
    expect(loadSession().status).toBe("discarded");
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ ...session, lead: { email: "a@b.com" } }));
    expect(loadSession().status).toBe("discarded");
  });

  it("nunca guarda algo fuera de esquema (p. ej. un lead)", () => {
    saveSession({ ...session, email: "a@b.com" } as never);
    expect(window.sessionStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it("funciona en memoria si sessionStorage lanza", () => {
    vi.spyOn(window.sessionStorage.__proto__, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    saveSession(session);
    expect(loadSession().status).toBe("restored");
    clearSession();
    expect(loadSession().status).toBe("empty");
  });
});
