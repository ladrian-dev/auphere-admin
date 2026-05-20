import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QAThread } from "@/lib/qa-api";

import { InspectorDrawer } from "../inspector-drawer";

function thread(over: Partial<QAThread> = {}): QAThread {
  return {
    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    tenant_id: "tn",
    operator_id: "op",
    external_id: null,
    title: "Audit me",
    archived_at: null,
    last_run_at: null,
    message_count: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...over,
  };
}

describe("InspectorDrawer", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the 5 tabs in the right order", () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    } as Response);
    render(<InspectorDrawer tenantId="tn" thread={null} />);
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual(["Tools", "Reasoning", "Trace", "Cost", "Audit"]);
  });

  it("Audit tab guides operator when no thread is selected", () => {
    render(<InspectorDrawer tenantId="tn" thread={null} />);
    expect(
      screen.getByText(/Seleccioná o creá una conversación/),
    ).toBeInTheDocument();
  });

  it("Audit tab fetches /api/qa/threads/[id]/audit and renders rows", async () => {
    const t = thread();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: "row-1",
          tool_name: "booking.create_appointment",
          tool_args: { date: "tomorrow" },
          synthetic_result: { ok: true },
          blocked_reason: "dry_run",
          run_id: "run-001",
          created_at: new Date().toISOString(),
        },
      ],
    } as Response);
    render(<InspectorDrawer tenantId="tn" thread={t} />);
    expect(
      await screen.findByText("booking.create_appointment"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/qa/threads/${t.id}/audit`,
      expect.any(Object),
    );
  });

  it("live tabs show empty-state copy when no runtime is bound", async () => {
    // ADR-021 Fase 2: Tools / Reasoning / Cost / Trace are live tabs
    // backed by the streaming runtime. Without a ``qaRuntime`` prop the
    // empty state explains that no turn has run yet.
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    } as Response);
    render(<InspectorDrawer tenantId="tn" thread={null} />);
    await userEvent.click(screen.getByRole("tab", { name: "Tools" }));
    expect(
      screen.getByText(/Aún no se ha ejecutado ningún turno/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Cost" }));
    expect(
      screen.getByText(/Aún no se ha ejecutado ningún turno/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Trace" }));
    expect(screen.getByText(/Link al trace en Langfuse/)).toBeInTheDocument();
  });
});
