import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { messages } from "@/i18n/messages";
import { DIAGNOSTIC_KEYS, WHAT_TO_DO, SUGGESTED_ACTIONS, type Diagnostics } from "@/lib/backend/channels";

import { qualityTone } from "../channel-card";
import { DiagnosticsTable, renderDetail, rowLabelKey, todoKey } from "../diagnostics-table";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({ testSendAction: vi.fn() }));

const data: Diagnostics = {
  checked_at: "2026-08-15T12:00:00Z",
  healthy: false,
  rows: [
    { key: "credentials", state: "fail", what_to_do: "connect_whatsapp", detail: null, link: null },
    { key: "quality", state: "warn", what_to_do: "improve_quality", detail: "YELLOW", link: "https://business.facebook.com/wa/manage/home/" },
    { key: "health_check", state: "ok", what_to_do: "none", detail: "2026-08-15T10:00:00Z", link: null },
    { key: "billing", state: "unknown", what_to_do: "check_meta_billing", detail: null, link: "https://business.facebook.com/billing_hub/accounts" },
  ],
};

describe("DiagnosticsTable (CP-19)", () => {
  it("renders every row with translated label, state and what-to-do", () => {
    render(
      <LocaleProvider locale="es">
        <DiagnosticsTable refId="demo" data={data} manage />
      </LocaleProvider>,
    );
    expect(screen.getByText("Hay fallos que atender")).toBeInTheDocument();
    expect(screen.getByText("Credenciales de Meta (token)")).toBeInTheDocument();
    expect(screen.getByText("Conecta WhatsApp desde la pestaña Canales.")).toBeInTheDocument();
    expect(screen.getByText("YELLOW")).toBeInTheDocument();
    expect(screen.getAllByText("Abrir en Meta")).toHaveLength(2);
    expect(screen.getByLabelText("Número destino (E.164)")).toBeInTheDocument();
  });
  it("hides the test-send form for read-only roles", () => {
    render(
      <LocaleProvider locale="en">
        <DiagnosticsTable refId="demo" data={data} manage={false} />
      </LocaleProvider>,
    );
    expect(screen.queryByText("Send test")).toBeNull();
    expect(screen.getByText("There are failures to fix")).toBeInTheDocument();
  });
  it("every backend code has an ES/EN message", () => {
    for (const k of DIAGNOSTIC_KEYS) expect(rowLabelKey(k) in messages, k).toBe(true);
    for (const c of WHAT_TO_DO) expect(todoKey(c) in messages, c).toBe(true);
    for (const a of SUGGESTED_ACTIONS) expect(`tpl.action.${a}` in messages, a).toBe(true);
    expect(rowLabelKey("made_up")).toBe("diag.row.channel");
    expect(todoKey("made_up")).toBe("diag.todo.none");
  });
  it("formats ISO details as dates and maps quality tones", () => {
    expect(renderDetail(data.rows[2]!, "en")).not.toContain("T10:00");
    expect(renderDetail(data.rows[1]!, "en")).toBe("YELLOW");
    expect(renderDetail(data.rows[0]!, "en")).toBe("—");
    expect(qualityTone("GREEN")).toBe("positive");
    expect(qualityTone("RED")).toBe("danger");
    expect(qualityTone(null)).toBe("muted");
  });
});
