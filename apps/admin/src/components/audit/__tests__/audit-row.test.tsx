import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AuditLogOut } from "@/lib/backend";

import { AuditRow } from "../audit-row";

function entry(overrides: Partial<AuditLogOut> = {}): AuditLogOut {
  return {
    id: "row-1",
    tenant_id: "tnt-1",
    actor: "luis",
    action: "agent_config.promote",
    target: "agent_config:v3",
    before_json: null,
    after_json: null,
    created_at: "2026-05-24T16:00:00Z",
    ...overrides,
  };
}

describe("AuditRow — humanizes action names", () => {
  it("translates known actions to verb phrases", () => {
    render(<AuditRow entry={entry({ action: "connector.connected" })} />);
    expect(screen.getByText(/conectó el connector/)).toBeInTheDocument();
  });

  it("falls back to raw action when unknown", () => {
    render(<AuditRow entry={entry({ action: "weird.custom.event" })} />);
    expect(screen.getByText("weird.custom.event")).toBeInTheDocument();
  });
});

describe("AuditRow — expand/collapse", () => {
  it("row without diff is not clickable to expand", () => {
    render(<AuditRow entry={entry({ before_json: null, after_json: null })} />);
    const row = screen.getByTestId("audit-row-row-1");
    const button = row.querySelector("button");
    expect(button).toBeDisabled();
    expect(screen.queryByTestId("audit-diff-row-1")).not.toBeInTheDocument();
  });

  it("row with diff toggles the diff panel on click", async () => {
    render(
      <AuditRow
        entry={entry({
          before_json: { runtime_memory_tool: false },
          after_json: { runtime_memory_tool: true },
        })}
      />,
    );
    expect(screen.queryByTestId("audit-diff-row-1")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("audit-row-row-1").querySelector("button")!);
    expect(screen.getByTestId("audit-diff-row-1")).toBeInTheDocument();
    expect(screen.getByText("Antes")).toBeInTheDocument();
    expect(screen.getByText("Después")).toBeInTheDocument();
  });

  it("renders only the 'after' side when before_json is null", async () => {
    render(
      <AuditRow
        entry={entry({
          action: "connector.connected",
          before_json: null,
          after_json: { status: "connected" },
        })}
      />,
    );
    await userEvent.click(screen.getByTestId("audit-row-row-1").querySelector("button")!);
    expect(screen.getByText("Resultado")).toBeInTheDocument();
    expect(screen.queryByText("Antes")).not.toBeInTheDocument();
  });

  it("renders only the 'before' side when after_json is null", async () => {
    render(
      <AuditRow
        entry={entry({
          action: "tenant.deleted",
          before_json: { status: "active" },
          after_json: null,
        })}
      />,
    );
    await userEvent.click(screen.getByTestId("audit-row-row-1").querySelector("button")!);
    expect(screen.getByText("Estado previo")).toBeInTheDocument();
    expect(screen.queryByText("Después")).not.toBeInTheDocument();
  });
});

describe("AuditRow — content surfaces", () => {
  it("shows actor as a badge", () => {
    render(<AuditRow entry={entry({ actor: "admin:abc12345" })} />);
    expect(screen.getByText("admin:abc12345")).toBeInTheDocument();
  });

  it("shows target as code", () => {
    render(<AuditRow entry={entry({ target: "connector:woocommerce" })} />);
    expect(screen.getByText("connector:woocommerce")).toBeInTheDocument();
  });
});
