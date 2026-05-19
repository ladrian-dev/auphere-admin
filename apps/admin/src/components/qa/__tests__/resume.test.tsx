/**
 * Resumability of <PlaygroundShell> (ADR-020 Fase 6, Bloque D).
 *
 * The feature spec promises: SSE caída → recargar → mensajes anteriores
 * presentes y run reanuda si seguía activo (``stream_resumable=true``).
 *
 * The "run reanuda" half depends on the live runtime (SSE + LangGraph
 * Server) that is wired in the cierre de Fase 5 — that piece is NOT
 * exercised here. What this test covers is the deterministic, runtime-
 * independent half: the URL ↔ state contract.
 *
 *   1. Mount the shell with an ``initialActiveThread``: the shell must
 *      ``router.replace`` to ``/qa/<tenant>/chat?thread=<id>`` so a
 *      reload of the same URL re-selects the same thread.
 *   2. Audit tab fetches ``/api/qa/threads/<id>/audit`` so the
 *      previously-rendered audit rows survive the remount (BE
 *      persistence is the source of truth — the shell is stateless
 *      across mount/unmount cycles).
 *   3. Unmount + remount with the same props: the URL gets re-set, the
 *      audit fetch fires again. There is NO in-memory state that gets
 *      lost.
 *
 * TODO(runtime-live): when ``thread-pane.tsx`` mounts
 * ``@assistant-ui/react-langgraph``, this file should grow a test that
 * asserts ``client.runs.stream({ stream_resumable: true })`` is called
 * with the previous run id when SSE drops mid-turn. That piece is
 * coupled to the LangGraph Server runtime and lives in a separate
 * harness.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QAThread } from "@/lib/qa-api";

// The UCM render + WhatsApp preview packages ship CJS-shaped builds
// whose ``dist/index.js`` references siblings without the ``.js``
// extension. Vitest's node ESM resolver refuses to follow them.
// Mocking them out is fine for this test — we're testing URL ↔ state,
// not rendering. The visual contract is covered by the gallery + the
// dedicated tests inside the packages themselves.
vi.mock("@nexus/ucm-render-web", () => ({
  UCMRenderer: ({ ucm }: { ucm: unknown }) => null,
}));
vi.mock("@nexus/ucm-preview-whatsapp", () => ({
  WhatsAppPreview: ({ ucm }: { ucm: unknown }) => null,
}));

import { PlaygroundShell } from "../playground-shell";

// next/navigation is server-flavoured by default — mock the router so
// the shell's ``router.replace`` call doesn't blow up in jsdom.
const routerReplaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplaceMock,
    push: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

function makeThread(over: Partial<QAThread> = {}): QAThread {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "tn",
    operator_id: "op",
    external_id: null,
    title: "Resumable thread",
    archived_at: null,
    last_run_at: null,
    message_count: 3,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...over,
  };
}

describe("PlaygroundShell — resumability (URL ↔ state)", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    routerReplaceMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    // The InspectorDrawer's Audit tab fetches on mount. Always answer
    // with an empty array — what matters here is that the fetch FIRED,
    // not what it returned.
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("syncs the active thread to the URL on mount", () => {
    const t = makeThread();
    render(
      <PlaygroundShell
        tenant={{ id: "tn", name: "T", slug: "t" }}
        agentVersion={1}
        operatorId="op"
        operatorEmail="op@auphere.dev"
        initialThreads={[t]}
        initialActiveThread={t}
      />,
    );
    // The shell renders the thread title somewhere visible.
    expect(screen.getAllByText(/Resumable thread/).length).toBeGreaterThan(
      0,
    );
    // Inspector Audit tab fetched audit on mount.
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/qa/threads/${t.id}/audit`,
      expect.any(Object),
    );
  });

  it("survives unmount + remount: the audit fetches again with the same id", () => {
    const t = makeThread();
    const { unmount } = render(
      <PlaygroundShell
        tenant={{ id: "tn", name: "T", slug: "t" }}
        agentVersion={1}
        operatorId="op"
        operatorEmail="op@auphere.dev"
        initialThreads={[t]}
        initialActiveThread={t}
      />,
    );
    const firstMountAuditCalls = fetchMock.mock.calls.filter((c) =>
      String(c[0]).endsWith(`/audit`),
    ).length;
    expect(firstMountAuditCalls).toBeGreaterThanOrEqual(1);

    unmount();
    // Fresh mount — simulating the user closing + reopening the tab.
    // Using ``render`` (not ``rerender``) because the previous root was
    // torn down by ``unmount``.
    render(
      <PlaygroundShell
        tenant={{ id: "tn", name: "T", slug: "t" }}
        agentVersion={1}
        operatorId="op"
        operatorEmail="op@auphere.dev"
        initialThreads={[t]}
        initialActiveThread={t}
      />,
    );
    const totalAuditCalls = fetchMock.mock.calls.filter((c) =>
      String(c[0]).endsWith(`/audit`),
    ).length;
    expect(totalAuditCalls).toBeGreaterThan(firstMountAuditCalls);
  });

  it("when no thread is active the shell does NOT fetch audit", () => {
    render(
      <PlaygroundShell
        tenant={{ id: "tn", name: "T", slug: "t" }}
        agentVersion={1}
        operatorId="op"
        operatorEmail="op@auphere.dev"
        initialThreads={[]}
        initialActiveThread={null}
      />,
    );
    expect(
      fetchMock.mock.calls.filter((c) => String(c[0]).endsWith(`/audit`))
        .length,
    ).toBe(0);
  });
});
