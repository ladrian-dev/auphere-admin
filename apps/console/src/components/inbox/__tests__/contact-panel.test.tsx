import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { ContactPanel } from "../contact-panel";
import { ME, NOW, detail, message } from "./fixtures";
import { InboxViewRef, renderInbox, resetActions } from "./view-harness";

vi.mock("@/app/(console)/inbox/actions", async () => (await import("./view-harness")).a);
InboxViewRef.current = (await import("../inbox-view")).InboxView;

function view(o: Partial<Parameters<typeof ContactPanel>[0]> = {}) {
  const props = {
    detail: detail(),
    initials: "AT",
    suggested: [] as string[],
    now: NOW,
    onClose: vi.fn(),
    onTags: vi.fn(async () => true),
    onNote: vi.fn(async () => true),
    ...o,
  };
  render(
    <LocaleProvider locale="es">
      <ContactPanel {...props} />
    </LocaleProvider>,
  );
  return props;
}

/** Spec 030 (R13, T078): the contact panel, each block present only with its data. */
describe("ContactPanel", () => {
  it("without an escalation there is no summary section", () => {
    view();
    expect(screen.queryByText("Resumen del agente")).toBeNull();
    expect(screen.getByText("Datos de contacto")).toBeInTheDocument();
    expect(screen.getByText("Sin actividad todavía.")).toBeInTheDocument();
  });

  it("with one, what the agent understood — and the activity, newest first", () => {
    view({
      detail: detail({
        summary: "Compró el lunes y pide el reembolso",
        activity: [
          { kind: "takeover", at: "2026-10-08T11:00:00Z", actor: ME, detail: null },
          { kind: "escalated", at: "2026-10-08T10:00:00Z", actor: { kind: "agent", name: null, is_me: false }, detail: "Pide un reembolso" },
        ],
      }),
    });
    expect(screen.getByText("Resumen del agente")).toBeInTheDocument();
    expect(screen.getByText("Compró el lunes y pide el reembolso")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toContain("Tomaste el control");
    expect(items[1]).toContain("El agente pidió ayuda: Pide un reembolso");
  });

  it("tags: remove, add, take a suggestion; a refusal puts them back", async () => {
    const onTags = vi.fn(async () => true);
    view({ detail: detail({ tags: ["VIP"] }), suggested: ["VIP", "Reembolso"], onTags });
    await userEvent.click(screen.getByRole("button", { name: "Quitar VIP" }));
    expect(onTags).toHaveBeenLastCalledWith([]);
    await userEvent.type(screen.getByRole("textbox", { name: "Agregar etiqueta" }), "  Mayorista  {Enter}");
    expect(onTags).toHaveBeenLastCalledWith(["Mayorista"]);
    await userEvent.click(screen.getByRole("button", { name: "+ Reembolso" }));
    expect(onTags).toHaveBeenLastCalledWith(["Mayorista", "Reembolso"]);

    onTags.mockResolvedValueOnce(false);
    await userEvent.click(screen.getByRole("button", { name: "Quitar Mayorista" }));
    expect(await screen.findByRole("button", { name: "Quitar Mayorista" })).toBeInTheDocument();
  });

  it("the note: saving, saved, and an error that does not lose the text", async () => {
    let finish!: (ok: boolean) => void;
    const onNote = vi.fn(() => new Promise<boolean>((r) => (finish = r)));
    view({ onNote });
    const box = screen.getByRole("textbox", { name: "Notas internas" });
    await userEvent.type(box, "Prefiere que le llamen");
    await userEvent.click(screen.getByRole("button", { name: "Guardar nota" }));
    expect(screen.getByText("Guardando…")).toBeInTheDocument();
    finish(true);
    expect(await screen.findByText("Guardada")).toBeInTheDocument();

    onNote.mockImplementationOnce(async () => false);
    await userEvent.type(box, " por la tarde");
    await userEvent.click(screen.getByRole("button", { name: "Guardar nota" }));
    expect(await screen.findByText("No se pudo guardar")).toBeInTheDocument();
    expect(box).toHaveValue("Prefiere que le llamen por la tarde");
  });
});

function setWidth(width: number) {
  Object.defineProperty(window, "innerWidth", { value: width, configurable: true });
  window.matchMedia = ((query: string) => ({
    matches: /min-width:\s*1280px/.test(query) ? width >= 1280 : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

const ID = "11111111-1111-4111-8111-111111111111";
const opened = () => ({ detail: detail(), thread: { items: [message()], next_before: null } });

describe("the panel: a column from 1280 px, a modal sheet below", () => {
  beforeEach(() => {
    resetActions();
    window.localStorage.clear();
  });

  it("wide: opens beside the thread and stays open next time", async () => {
    setWidth(1440);
    window.localStorage.setItem("nexus.inbox.panel", "closed");
    const first = renderInbox({ selectedId: ID, open: opened() });
    expect(screen.queryByRole("complementary", { name: "Datos del contacto" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Datos del contacto" }));
    expect(screen.getByRole("complementary", { name: "Datos del contacto" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(window.localStorage.getItem("nexus.inbox.panel")).toBe("open");
    first.unmount();

    renderInbox({ selectedId: ID, open: opened() });
    await waitFor(() => expect(screen.getByRole("complementary", { name: "Datos del contacto" })).toBeInTheDocument());
  });

  it("narrow: a modal sheet that holds the focus, closes with Escape and is not remembered", async () => {
    setWidth(1024);
    renderInbox({ selectedId: ID, open: opened() });
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Datos del contacto" }));
    const sheet = await screen.findByRole("dialog", { name: "Datos del contacto" });
    expect(sheet).toBeInTheDocument();
    expect(window.localStorage.getItem("nexus.inbox.panel")).toBeNull();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("decides by the Inbox's own width, not the window's (sidebar open at 1440 px)", async () => {
    setWidth(1440);
    window.localStorage.setItem("nexus.inbox.panel", "open");
    class NarrowObserver {
      constructor(private cb: ResizeObserverCallback) {}
      observe() {
        this.cb([{ contentRect: { width: 900 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
      }
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal("ResizeObserver", NarrowObserver);
    renderInbox({ selectedId: ID, open: opened() });
    // Remembered «open», but there is no room for a column: nothing covers the thread.
    expect(screen.queryByRole("complementary", { name: "Datos del contacto" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Datos del contacto" }));
    expect(await screen.findByRole("dialog", { name: "Datos del contacto" })).toBeInTheDocument();
    vi.unstubAllGlobals();
    vi.stubGlobal("EventSource", (await import("./view-harness")).FakeEventSource);
  });

  it("works with storage blocked (private window): it just does not remember", async () => {
    setWidth(1440);
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderInbox({ selectedId: ID, open: { detail: detail(), thread: { items: [], next_before: null } } });
    // Whatever this tab remembered, the toggle still flips it.
    const wasOpen = screen.queryByRole("complementary", { name: "Datos del contacto" }) !== null;
    // Open, there are two ways to hide it (the header's toggle and the panel's own X).
    await userEvent.click(screen.getAllByRole("button", { name: wasOpen ? "Ocultar datos del contacto" : "Datos del contacto" })[0]!);
    expect(screen.queryByRole("complementary", { name: "Datos del contacto" }) !== null).toBe(!wasOpen);
    spy.mockRestore();
  });
});
