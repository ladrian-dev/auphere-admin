import { describe, expect, it } from "vitest";

import { messages } from "@/i18n/messages";

import { contextId, readPageContext, suggestionKeys } from "../page-context";

describe("readPageContext", () => {
  it("splits a client route into ref and tab", () => {
    expect(readPageContext("/clients/boreal/agent/settings")).toEqual({
      route: "/clients/boreal/agent/settings",
      client_ref: "boreal",
      tab: "agent/settings",
      selection: null,
    });
  });

  it("does NOT treat /clients/new as a client ref", () => {
    // Otherwise the Companion would talk about a client that does not exist.
    expect(readPageContext("/clients/new").client_ref).toBeNull();
  });

  it("decodes an encoded ref and survives a malformed one", () => {
    expect(readPageContext("/clients/cl%C3%ADnica/agent").client_ref).toBe("clínica");
    expect(readPageContext("/clients/%E0%A4%A/agent").client_ref).toBe("%E0%A4%A");
  });

  it("carries no client for partner-level routes", () => {
    expect(readPageContext("/usage/alerts")).toMatchObject({ client_ref: null, tab: "alerts" });
    expect(readPageContext("/")).toMatchObject({ client_ref: null, tab: null });
  });
});

describe("contextId", () => {
  it.each([
    ["/", "home"],
    ["/clients", "clients"],
    ["/clients/new", "clients"],
    ["/clients/boreal", "client"],
    ["/clients/boreal/agent", "agent"],
    ["/clients/boreal/agent/settings", "agentSettings"],
    ["/clients/boreal/tools", "tools"],
    ["/clients/boreal/skills", "skills"],
    ["/clients/boreal/knowledge", "knowledge"],
    ["/clients/boreal/channels", "channels"],
    ["/clients/boreal/channels/diagnostics", "channels"],
    ["/clients/boreal/playground", "playground"],
    ["/clients/boreal/conversations", "conversations"],
    ["/usage", "usage"],
    ["/audit", "audit"],
    ["/team", "team"],
    ["/keys", "keys"],
    ["/billing", "billing"],
  ])("maps %s to %s", (path, expected) => {
    expect(contextId(readPageContext(path))).toBe(expected);
  });
});

describe("suggestionKeys — §14 forbids generic suggestions", () => {
  it("gives three keys that all exist in both languages", () => {
    for (const path of ["/", "/clients/boreal/channels", "/usage", "/billing"]) {
      const keys = suggestionKeys(readPageContext(path));
      expect(keys).toHaveLength(3);
      for (const key of keys) {
        expect(messages[key], `${String(key)} missing`).toBeDefined();
        expect(messages[key].es.length).toBeGreaterThan(0);
        expect(messages[key].en.length).toBeGreaterThan(0);
      }
    }
  });

  it("gives DIFFERENT suggestions on a channels page than on a usage page", () => {
    // This is the whole requirement: the empty state must be derived from
    // where the user is standing, not a fixed trio.
    const channels = suggestionKeys(readPageContext("/clients/boreal/channels"));
    const usage = suggestionKeys(readPageContext("/usage"));
    expect(channels).not.toEqual(usage);
    expect(messages[channels[0]].es).toContain("calidad");
    expect(messages[usage[0]].es).toContain("consumo");
  });
});
