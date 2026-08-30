import { describe, expect, it } from "vitest";

import { defaultNewKeyForm } from "../key-defaults";

describe("defaultNewKeyForm (QA-20)", () => {
  it("defaults to test (Pruebas) with empty scopes", () => {
    expect(defaultNewKeyForm()).toEqual({ type: "test", scopes: [] });
  });
});
