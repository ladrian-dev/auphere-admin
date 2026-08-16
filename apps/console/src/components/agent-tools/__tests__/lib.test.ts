import { describe, expect, it } from "vitest";

import { messages } from "@/i18n/messages";
import { KNOWLEDGE_ERROR_CODES, TOOL_MODES, type ToolOut } from "@/lib/backend/agent-tools-types";

import {
  CONNECTOR_STATUS_KEYS,
  connectorStatusKey,
  connectorTone,
  groupToolsByConnector,
  knowledgeErrorKey,
  knowledgeStatusTone,
  knowledgeUsageRatio,
  splitCredentials,
  usageWidthClass,
} from "../lib";

const tool = (name: string, slug: string | null, display: string | null = slug): ToolOut => ({
  name,
  description: "",
  capability_tags: [],
  read_only: false,
  destructive: false,
  status: "active",
  enabled: false,
  enabled_in_active: false,
  connector_slug: slug,
  connector_display_name: display,
  connector_status: null,
  connector_required: slug !== null,
  usable: true,
  default_mode: "always",
  override_mode: null,
  effective_mode: "always",
});

describe("groupToolsByConnector", () => {
  it("puts native tools first, then connectors alphabetically, tools sorted", () => {
    const groups = groupToolsByConnector([tool("z_native", null), tool("shop_orders", "shopify", "Shopify"), tool("cal_free", "google_calendar", "Google Calendar"), tool("a_native", null), tool("shop_products", "shopify", "Shopify")]);
    expect(groups.map((g) => g.slug)).toEqual([null, "google_calendar", "shopify"]);
    expect(groups[0]?.tools.map((x) => x.name)).toEqual(["a_native", "z_native"]);
    expect(groups[2]?.tools.map((x) => x.name)).toEqual(["shop_orders", "shop_products"]);
  });
  it("empty in, empty out", () => {
    expect(groupToolsByConnector([])).toEqual([]);
  });
});

describe("connector helpers", () => {
  it("maps statuses to tones and message keys that exist in ES/EN", () => {
    expect(connectorTone("connected")).toBe("positive");
    expect(connectorTone("paused")).toBe("warning");
    expect(connectorTone("error")).toBe("danger");
    expect(connectorTone(null)).toBe("muted");
    for (const s of CONNECTOR_STATUS_KEYS) expect(connectorStatusKey(s) in messages, s).toBe(true);
    expect(connectorStatusKey(null)).toBe("connectors.status.none");
    expect(connectorStatusKey("weird")).toBe("connectors.status.none");
    for (const m of TOOL_MODES) expect(`tools.mode.${m}` in messages, m).toBe(true);
  });
  it("splits credentials into secrets vs endpoint_meta and drops blanks", () => {
    const out = splitCredentials(
      [
        { field: "api_key", secret: true, required: true },
        { field: "shop_domain", secret: false },
        { field: "optional", secret: false },
      ],
      { api_key: " k1 ", shop_domain: "acme.myshopify.com", optional: "" },
    );
    expect(out).toEqual({ secrets: { api_key: "k1" }, endpoint_meta: { shop_domain: "acme.myshopify.com" } });
  });
});

describe("knowledge helpers", () => {
  it("every backend error_code has an explanation, unknown falls back", () => {
    for (const c of KNOWLEDGE_ERROR_CODES) expect(knowledgeErrorKey(c) in messages, c).toBe(true);
    expect(knowledgeErrorKey("made_up")).toBe("knowledge.error.unknown");
    expect(knowledgeErrorKey(null)).toBe("knowledge.error.unknown");
  });
  it("status tones and usage ratio", () => {
    expect(knowledgeStatusTone("indexed")).toBe("positive");
    expect(knowledgeStatusTone("failed")).toBe("danger");
    expect(knowledgeStatusTone("pending")).toBe("info");
    expect(knowledgeUsageRatio(50, 100)).toBe(0.5);
    expect(knowledgeUsageRatio(500, 100)).toBe(1);
    expect(knowledgeUsageRatio(5, 0)).toBe(0);
  });
  it("width class steps", () => {
    expect(usageWidthClass(0)).toBe("w-0");
    expect(usageWidthClass(0.01)).toBe("w-1/12");
    expect(usageWidthClass(0.5)).toBe("w-6/12");
    expect(usageWidthClass(1)).toBe("w-full");
    expect(usageWidthClass(3)).toBe("w-full");
  });
});
