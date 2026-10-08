import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { InboxThreadItem } from "@/lib/backend/inbox";

import { Thread } from "../thread";
import { ME, NOW, message } from "./fixtures";

function view(items: InboxThreadItem[], o: Partial<Parameters<typeof Thread>[0]> = {}) {
  const props = { items, hasOlder: false, loadingOlder: false, contactInitials: "AT", now: NOW, onOlder: vi.fn(), ...o };
  render(
    <LocaleProvider locale="es">
      <Thread {...props} />
    </LocaleProvider>,
  );
  return props;
}

/** Spec 030 (R8, T053): the thread says who wrote, what arrived and what happened. */
describe("Thread", () => {
  it("separates days and tells the authors apart", () => {
    view([
      message({ id: "1", at: "2026-10-07T10:00:00Z", text: "¿Abren mañana?" }),
      message({ id: "2", at: "2026-10-07T10:00:05Z", direction: "outbound", author: { kind: "agent", name: null, is_me: false }, text: "Sí, de 10 a 20 h.", delivery: "read" }),
      message({ id: "3", at: "2026-10-08T09:00:00Z", direction: "outbound", author: ME, text: "Te espero", delivery: "delivered" }),
    ]);
    expect(screen.getByRole("log", { name: "Mensajes" })).toBeInTheDocument();
    expect(screen.getByText("Ayer")).toBeInTheDocument();
    expect(screen.getByText("Hoy")).toBeInTheDocument();
    expect(screen.getByText(/Agente ·/)).toBeInTheDocument();
    expect(screen.getByText("· Leído")).toBeInTheDocument();
    expect(screen.getByText(/^Tú ·/)).toBeInTheDocument();
    expect(screen.getByText("· Entregado")).toBeInTheDocument();
  });

  it("an image is visible with its size fixed; a document says its name; an audio, its transcript", () => {
    view([
      message({ id: "img", text: null, media: { kind: "image", filename: "carta.jpg", transcript: null } }),
      message({ id: "doc", text: null, media: { kind: "document", filename: "presupuesto.pdf", transcript: null } }),
      message({ id: "aud", text: null, media: { kind: "audio", filename: null, transcript: "Quería saber el precio" } }),
    ]);
    const img = screen.getByRole("img", { name: "carta.jpg" });
    expect(img).toHaveAttribute("src", "/api/lite/inbox/media/img");
    expect(img).toHaveAttribute("width", "220");
    expect(img).toHaveAttribute("height", "148");
    expect(screen.getByRole("link", { name: "Abrir presupuesto.pdf" })).toHaveAttribute("href", "/api/lite/inbox/media/doc");
    expect(screen.getByText("Transcripción: Quería saber el precio")).toBeInTheDocument();
  });

  it("an image that does not load falls back to its file link, never a broken icon", () => {
    view([message({ id: "img", text: null, media: { kind: "image", filename: "carta.jpg", transcript: null } })]);
    fireEvent.error(screen.getByRole("img", { name: "carta.jpg" }));
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("link", { name: "Abrir carta.jpg" })).toHaveAttribute("href", "/api/lite/inbox/media/img");
  });

  it("a failed send says it failed and why", () => {
    view([
      message({ direction: "outbound", author: ME, text: "Hola", delivery: "failed", failure_reason: "fuera de la ventana de 24 h" }),
    ]);
    expect(screen.getByRole("status")).toHaveTextContent("No se envió: fuera de la ventana de 24 h");
  });

  it("what happened to the conversation sits in its place", () => {
    view([
      message({ id: "e1", type: "event", kind: "escalated", author: { kind: "agent", name: null, is_me: false }, detail: "Pide un reembolso", text: null }),
      message({ id: "e2", type: "event", kind: "takeover", author: ME, text: null }),
      message({ id: "e3", type: "event", kind: "reopened", author: { kind: "contact", name: null, is_me: false }, text: null }),
    ]);
    expect(screen.getByRole("note")).toHaveTextContent("El agente pidió ayuda: Pide un reembolso");
    expect(screen.getByText(/^Tomaste el control ·/)).toBeInTheDocument();
    expect(screen.queryByText(/Tú tomó/)).toBeNull();
    expect(screen.getByText(/El contacto volvió a escribir y se reabrió/)).toBeInTheDocument();
  });

  it("offers earlier messages when there are more", () => {
    const props = view([message()], { hasOlder: true });
    screen.getByRole("button", { name: "Ver mensajes anteriores" }).click();
    expect(props.onOlder).toHaveBeenCalled();
  });
});
