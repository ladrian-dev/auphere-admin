import { describe, expect, it } from "vitest";

import { messages } from "@/i18n/messages";
import { ESCALATION_TRIGGERS, TONES, WEEKDAYS } from "@/lib/backend/agent-tools-types";

import {
  buildConsolePolicySchema,
  consolePolicySchema,
  defaultConsolePolicy,
  groupSlotsByDay,
  isValidTimezone,
  parseLanguageList,
} from "../settings-schema";

describe("consolePolicySchema (mirror of agent_console_policy.ConsolePolicy)", () => {
  it("accepts the default policy and fills defaults for a bare object", () => {
    expect(consolePolicySchema.safeParse(defaultConsolePolicy()).success).toBe(true);
    const parsed = consolePolicySchema.parse({});
    expect(parsed.schema_version).toBe(1);
    expect(parsed.tone.style).toBe("cercano");
    expect(parsed.escalation.triggers).toEqual(["user_asks_human", "angry", "out_of_scope"]);
    expect(parsed.ai_disclosure.enabled).toBe(true);
  });
  it("rejects a slot whose open >= close and a bad time format", () => {
    const bad = { ...defaultConsolePolicy(), schedule: { timezone: "UTC", weekly: [{ day: "mon", open: "18:00", close: "09:00" }], closed_message: "" } };
    const res = consolePolicySchema.safeParse(bad);
    expect(res.success).toBe(false);
    if (!res.success) expect(res.error.issues.some((i) => i.path.join(".") === "schedule.weekly.0.close")).toBe(true);
    const badTime = { ...defaultConsolePolicy(), schedule: { timezone: "UTC", weekly: [{ day: "mon", open: "9:00", close: "18:00" }], closed_message: "" } };
    expect(consolePolicySchema.safeParse(badTime).success).toBe(false);
    const ok = { ...defaultConsolePolicy(), schedule: { timezone: "Europe/Madrid", weekly: [{ day: "mon", open: "09:00", close: "18:00" }], closed_message: "" } };
    expect(consolePolicySchema.safeParse(ok).success).toBe(true);
  });
  it("requires after_n_turns when the trigger is on", () => {
    const p = defaultConsolePolicy();
    p.escalation.triggers = ["after_n_turns"];
    expect(consolePolicySchema.safeParse(p).success).toBe(false);
    p.escalation.after_n_turns = 8;
    expect(consolePolicySchema.safeParse(p).success).toBe(true);
    p.escalation.after_n_turns = 101;
    expect(consolePolicySchema.safeParse(p).success).toBe(false);
  });
  it("validates timezones and rejects unknown keys (extra=forbid)", () => {
    expect(isValidTimezone("Europe/Madrid")).toBe(true);
    expect(isValidTimezone("Mars/Olympus")).toBe(false);
    const p = { ...defaultConsolePolicy(), schedule: { timezone: "Mars/Olympus", weekly: [], closed_message: "" } };
    expect(consolePolicySchema.safeParse(p).success).toBe(false);
    expect(consolePolicySchema.safeParse({ ...defaultConsolePolicy(), extra: 1 }).success).toBe(false);
  });
  it("uses injected messages", () => {
    const schema = buildConsolePolicySchema({ timezone: "TZ!" });
    const res = schema.safeParse({ ...defaultConsolePolicy(), schedule: { timezone: "Nope/Nope", weekly: [], closed_message: "" } });
    expect(res.success).toBe(false);
    if (!res.success) expect(res.error.issues[0]?.message).toBe("TZ!");
  });
  it("every enum value has ES/EN labels", () => {
    for (const d of WEEKDAYS) expect(`agentSettings.day.${d}` in messages, d).toBe(true);
    for (const x of TONES) expect(`agentSettings.tone.${x}` in messages, x).toBe(true);
    for (const x of ESCALATION_TRIGGERS) expect(`agentSettings.escalation.trigger.${x}` in messages, x).toBe(true);
  });
});

describe("groupSlotsByDay / parseLanguageList", () => {
  it("groups in Monday→Sunday order and keeps flat indexes", () => {
    const groups = groupSlotsByDay([
      { day: "wed", open: "09:00", close: "13:00" },
      { day: "mon", open: "09:00", close: "18:00" },
      { day: "wed", open: "15:00", close: "19:00" },
    ]);
    expect(groups.map((g) => g.day)).toEqual([...WEEKDAYS]);
    expect(groups[0]?.slots.map((s) => s.index)).toEqual([1]);
    expect(groups[2]?.slots.map((s) => s.index)).toEqual([0, 2]);
    expect(groups[6]?.slots).toEqual([]);
  });
  it("parses language lists", () => {
    expect(parseLanguageList("es, EN;pt  es")).toEqual(["es", "en", "pt"]);
    expect(parseLanguageList("")).toEqual([]);
  });
});
