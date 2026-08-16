import { describe, expect, it } from "vitest";

import { parseAlertsForm } from "../usage-alerts-form";

describe("parseAlertsForm (CP-24)", () => {
  it("accepts an empty cap (no cap) and dedupes/lowercases recipients", () => {
    expect(parseAlertsForm({ cap: "", recipients: "Ops@x.com\nops@x.com, a@b.co", enabled: true })).toEqual({
      ok: true,
      value: { cap_messages_month: null, recipients: ["ops@x.com", "a@b.co"], enabled: true },
    });
  });
  it("accepts grouped digits and rejects garbage", () => {
    expect(parseAlertsForm({ cap: "5.000", recipients: "", enabled: false })).toEqual({ ok: true, value: { cap_messages_month: 5000, recipients: [], enabled: false } });
    expect(parseAlertsForm({ cap: "-3", recipients: "", enabled: true })).toEqual({ ok: false, error: "cap" });
    expect(parseAlertsForm({ cap: "abc", recipients: "", enabled: true })).toEqual({ ok: false, error: "cap" });
  });
  it("names the invalid e-mail", () => {
    expect(parseAlertsForm({ cap: "10", recipients: "ok@x.com\nnope", enabled: true })).toEqual({ ok: false, error: "email", email: "nope" });
  });
});
