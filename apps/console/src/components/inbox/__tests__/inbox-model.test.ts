import { describe, expect, it } from "vitest";

import { checkAttachment, composerMode, dayLabel, initialsOf, sendErrorOf, withDaySeparators } from "../inbox-model";
import { ME, NOW, detail, message } from "./fixtures";

/** Spec 030: the decisions the Inbox must not get wrong, without rendering. */
describe("composerMode", () => {
  it("offers what is possible, never a box that cannot send", () => {
    expect(composerMode(detail({ state: "resolved" }))).toEqual({ kind: "resolved" });
    expect(composerMode(detail({ state: "waiting", waiting_reason: "Pide un reembolso" }))).toEqual({
      kind: "waiting",
      reason: "Pide un reembolso",
    });
    expect(composerMode(detail({ state: "agent" }))).toEqual({ kind: "agent" });
    expect(composerMode(detail({ state: "person", assignee: { kind: "member", name: "Luis", is_me: false } }))).toEqual({
      kind: "other",
      name: "Luis",
    });
    expect(composerMode(detail({ state: "person", assignee: ME }))).toEqual({ kind: "mine", blocked: null });
  });

  it("says why WhatsApp would refuse a send", () => {
    expect(composerMode(detail({ state: "person", assignee: ME, window: { open: false, closes_at: null } }))).toEqual({
      kind: "mine",
      blocked: "window_closed",
    });
    expect(
      composerMode(detail({ state: "person", assignee: ME, channel: { kind: "whatsapp", connected: false } })),
    ).toEqual({ kind: "mine", blocked: "channel_disconnected" });
  });

  it("maps the API's send codes and nothing else", () => {
    expect(sendErrorOf("window_closed")).toBe("window_closed");
    expect(sendErrorOf("not_assigned_to_you")).toBe("not_assigned_to_you");
    expect(sendErrorOf("something_new")).toBe("generic");
    expect(sendErrorOf(null)).toBe("generic");
  });
});

describe("checkAttachment (R10.3)", () => {
  const MB = 1024 * 1024;
  it("takes JPEG/PNG up to 5 MB and PDF up to 16 MB", () => {
    expect(checkAttachment({ type: "image/jpeg", size: 5 * MB })).toEqual({ ok: true });
    expect(checkAttachment({ type: "image/png", size: 5 * MB + 1 })).toEqual({ ok: false, reason: "size", maxMb: 5 });
    expect(checkAttachment({ type: "application/pdf", size: 16 * MB })).toEqual({ ok: true });
    expect(checkAttachment({ type: "application/pdf", size: 16 * MB + 1 })).toEqual({ ok: false, reason: "size", maxMb: 16 });
  });
  it("refuses anything else by type", () => {
    expect(checkAttachment({ type: "image/gif", size: 10 })).toEqual({ ok: false, reason: "type" });
    expect(checkAttachment({ type: "", size: 10 })).toEqual({ ok: false, reason: "type" });
  });
});

describe("days and people", () => {
  it("reads today, yesterday and a date", () => {
    expect(dayLabel("2026-10-08T09:00:00Z", NOW, "es").kind).toBe("today");
    expect(dayLabel("2026-10-07T09:00:00Z", NOW, "es").kind).toBe("yesterday");
    const d = dayLabel("2026-09-20T09:00:00Z", NOW, "es");
    expect(d).toEqual({ kind: "date", text: "20 de septiembre" });
    expect(dayLabel("2025-09-20T09:00:00Z", NOW, "es")).toEqual({ kind: "date", text: "20 de septiembre de 2025" });
  });

  it("puts a separator wherever the day changes", () => {
    const rows = withDaySeparators([
      message({ id: "a", at: "2026-10-07T10:00:00Z" }),
      message({ id: "b", at: "2026-10-07T11:00:00Z" }),
      message({ id: "c", at: "2026-10-08T09:00:00Z" }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["day", "item", "item", "day", "item"]);
  });

  it("makes initials from names, not from phone numbers", () => {
    expect(initialsOf("Ana Torres")).toBe("AT");
    expect(initialsOf("ana")).toBe("A");
    expect(initialsOf("+54 9 11")).toBe("·");
    expect(initialsOf(null)).toBe("·");
  });
});
