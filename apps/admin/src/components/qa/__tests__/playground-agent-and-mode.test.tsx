/**
 * Fallo `playground-del-panel-sin-agente`, lado del panel.
 *
 * - La insignia del encabezado dice el modo del hilo en pantalla (ADR-024): «En vivo»
 *   con `dry_run = false`, «Dry run» en otro caso. Estaba escrita a mano.
 * - Spec 030 (R14.5): un hilo nuevo se abre con el agente elegido, y `?agent=` se
 *   conserva al cambiar de hilo.
 * - Los hilos que se listan son los del agente elegido; uno sin agente es del
 *   principal.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TenantAgent } from "@/lib/backend";
import type { QAThread } from "@/lib/qa-api";
import { pickPlaygroundAgent, shellAgent, threadsOfAgent } from "@/lib/qa-playground-agent";

vi.mock("@nexus/ucm-render-web", () => ({ UCMRenderer: () => null }));
vi.mock("@nexus/ucm-preview-whatsapp", () => ({ WhatsAppPreview: () => null }));

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

import { PlaygroundShell } from "../playground-shell";

const PRINCIPAL = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SALES = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

function thread(over: Partial<QAThread> = {}): QAThread {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "tn",
    agent_id: PRINCIPAL,
    operator_id: "op",
    external_id: null,
    title: "Hilo",
    dry_run: true,
    archived_at: null,
    last_run_at: null,
    message_count: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...over,
  };
}

function agent(over: Partial<TenantAgent> = {}): TenantAgent {
  return {
    id: PRINCIPAL,
    name: "Recepción",
    status: "active",
    is_principal: true,
    channels: [],
    active_version: 3,
    draft_version: null,
    ...over,
  };
}

function header(): HTMLElement {
  const root = document.querySelector("[data-qa-playground-root] header");
  if (!(root instanceof HTMLElement)) throw new Error("no header");
  return root;
}

describe("PlaygroundShell — modo y agente", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    routerReplaceMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue({ ok: true, json: async () => [] } as Response);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("dice «En vivo» en un hilo en vivo y «Dry run» en uno simulado", () => {
    const live = thread({ dry_run: false, title: "En vivo de verdad" });
    const { unmount } = render(
      <PlaygroundShell
        tenant={{ id: "tn", name: "T", slug: "t" }}
        agentVersion={3}
        operatorId="op"
        operatorEmail={null}
        initialThreads={[live]}
        initialActiveThread={live}
      />,
    );
    expect(within(header()).getByText("En vivo")).toBeInTheDocument();
    expect(within(header()).queryByText("Dry run")).not.toBeInTheDocument();
    unmount();

    const dry = thread();
    render(
      <PlaygroundShell
        tenant={{ id: "tn", name: "T", slug: "t" }}
        agentVersion={3}
        operatorId="op"
        operatorEmail={null}
        initialThreads={[dry]}
        initialActiveThread={dry}
      />,
    );
    expect(within(header()).getByText("Dry run")).toBeInTheDocument();
    expect(within(header()).queryByText("En vivo")).not.toBeInTheDocument();
  });

  it("abre el hilo nuevo con el agente elegido y conserva ?agent=", async () => {
    const created = thread({ id: "22222222-2222-2222-2222-222222222222", agent_id: SALES });
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/qa/threads" && init?.method === "POST") {
        return { ok: true, json: async () => created } as Response;
      }
      return { ok: true, json: async () => [] } as Response;
    });
    render(
      <PlaygroundShell
        tenant={{ id: "tn", name: "T", slug: "t" }}
        agent={{ id: SALES, name: "Ventas", query: SALES }}
        agentVersion={1}
        operatorId="op"
        operatorEmail={null}
        initialThreads={[]}
        initialActiveThread={null}
      />,
    );
    expect(within(header()).getByText(/Ventas v1/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "+ nueva" }));

    const post = fetchMock.mock.calls.find(
      ([url, init]) => url === "/api/qa/threads" && init?.method === "POST",
    );
    expect(post).toBeDefined();
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      tenant_id: "tn",
      agent_id: SALES,
    });
    expect(routerReplaceMock).toHaveBeenLastCalledWith(
      `/qa/tn/chat?agent=${SALES}&thread=${created.id}`,
      { scroll: false },
    );
  });

  it("al cambiar de agente enseña sus hilos sin volver a montar el shell", () => {
    const mine = thread({ id: "p1", title: "Del principal" });
    const theirs = thread({ id: "s1", title: "De ventas", agent_id: SALES });
    const props = {
      tenant: { id: "tn", name: "T", slug: "t" },
      agentVersion: 1,
      operatorId: "op",
      operatorEmail: null,
    };
    const { rerender } = render(
      <PlaygroundShell
        {...props}
        agent={{ id: PRINCIPAL, name: "Recepción", query: null }}
        initialThreads={[mine]}
        initialActiveThread={mine}
      />,
    );
    const root = document.querySelector("[data-qa-playground-root]");
    expect(screen.getAllByText("Del principal").length).toBeGreaterThan(0);

    rerender(
      <PlaygroundShell
        {...props}
        agent={{ id: SALES, name: "Ventas", query: SALES }}
        initialThreads={[theirs]}
        initialActiveThread={null}
      />,
    );
    expect(document.querySelector("[data-qa-playground-root]")).toBe(root);
    expect(screen.getByText("De ventas")).toBeInTheDocument();
    expect(screen.queryByText("Del principal")).not.toBeInTheDocument();
  });

  it("sin agente leído no manda agent_id: la API elige el principal", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === "/api/qa/threads" && init?.method === "POST") {
        return { ok: true, json: async () => thread() } as Response;
      }
      return { ok: true, json: async () => [] } as Response;
    });
    render(
      <PlaygroundShell
        tenant={{ id: "tn", name: "T", slug: "t" }}
        agentVersion={null}
        operatorId="op"
        operatorEmail={null}
        initialThreads={[]}
        initialActiveThread={null}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "+ nueva" }));
    const post = fetchMock.mock.calls.find(
      ([url, init]) => url === "/api/qa/threads" && init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).not.toHaveProperty("agent_id");
  });
});

describe("pickPlaygroundAgent / threadsOfAgent", () => {
  const agents = [agent(), agent({ id: SALES, name: "Ventas", is_principal: false })];

  it("elige el de ?agent= o, sin él o con uno ajeno, el principal", () => {
    expect(pickPlaygroundAgent(agents, SALES).selected?.id).toBe(SALES);
    expect(pickPlaygroundAgent(agents, undefined).selected?.id).toBe(PRINCIPAL);
    expect(pickPlaygroundAgent(agents, "otro").selected?.id).toBe(PRINCIPAL);
  });

  it("no ofrece un agente archivado", () => {
    const withArchived = [...agents, agent({ id: "c", is_principal: false, status: "archived" })];
    const picked = pickPlaygroundAgent(withArchived, "c");
    expect(picked.selected?.id).toBe(PRINCIPAL);
    expect(picked.agents.map((a) => a.id)).toEqual([PRINCIPAL, SALES]);
  });

  it("sin la lista no elige nada y se listan todos los hilos", () => {
    const picked = pickPlaygroundAgent(null, SALES);
    expect(picked.selected).toBeNull();
    expect(shellAgent(picked.selected)).toBeNull();
    const all = [thread(), thread({ id: "x", agent_id: SALES })];
    expect(threadsOfAgent(all, null)).toEqual(all);
  });

  it("los hilos sin agente son del principal", () => {
    const old = thread({ id: "old", agent_id: null });
    const mine = thread({ id: "mine", agent_id: SALES });
    const principals = thread({ id: "p" });
    const all = [old, mine, principals];
    expect(threadsOfAgent(all, agents[0] ?? null).map((t) => t.id)).toEqual(["old", "p"]);
    expect(threadsOfAgent(all, agents[1] ?? null).map((t) => t.id)).toEqual(["mine"]);
    expect(shellAgent(agents[0] ?? null)?.query).toBeNull();
    expect(shellAgent(agents[1] ?? null)?.query).toBe(SALES);
  });
});
