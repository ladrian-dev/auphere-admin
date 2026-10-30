import { describe, expect, it } from "vitest";

import { actionErrorText } from "../action-error";

const t = (key: string) => `<${key}>`;

describe("actionErrorText", () => {
  it("a 403 is 'you cannot', never the backend's word", () => {
    expect(actionErrorText({ ok: false, status: 403, message: "forbidden" }, t)).toBe("<common.forbidden>");
    expect(actionErrorText({ ok: false, status: 401, message: "no session" }, t)).toBe("<common.forbidden>");
  });
  it("our failures read as 'try again'", () => {
    expect(actionErrorText({ ok: false, status: 503, message: "upstream timeout at 10.0.0.3" }, t)).toBe("<common.error.backend>");
    expect(actionErrorText({ ok: false, status: 0, message: "" }, t)).toBe("<common.error.backend>");
  });
  it("a human 4xx passes through", () => {
    expect(actionErrorText({ ok: false, status: 409, message: "Ya existe un cliente con esa referencia" }, t)).toBe("Ya existe un cliente con esa referencia");
  });
});

/**
 * Spec 047, enmienda del 2026-10-30 (T228; `contracts/console-api.md` §11
 * «Códigos nuevos»): los códigos nuevos llegan a pantallas que usan esta
 * función (la barra de guardar de antes, el alta de agente de antes). La
 * frase la escribe la consola, nunca el `detail` de la API.
 */
describe("actionErrorText · solo lo que tenemos", () => {
  it("cada código nuevo con su frase, aunque la API mande otra cosa en `message`", () => {
    expect(actionErrorText({ ok: false, status: 409, message: "structured agent", code: "structured_agent" }, t)).toBe("<common.error.structured_agent>");
    expect(actionErrorText({ ok: false, status: 410, message: "gone", code: "seed_template_retired" }, t)).toBe("<common.error.seed_template_retired>");
    expect(actionErrorText({ ok: false, status: 422, message: "gone", code: "seed_template_retired" }, t)).toBe("<common.error.seed_template_retired>");
    expect(actionErrorText({ ok: false, status: 503, message: "facts", code: "facts_unavailable" }, t)).toBe("<common.error.facts_unavailable>");
  });
});
