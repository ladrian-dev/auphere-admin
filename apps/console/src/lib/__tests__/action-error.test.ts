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
