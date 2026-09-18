// @vitest-environment jsdom
/**
 * Requisitos 10.1, 10.5, 10.6 y 10.7 — decidir con lo necesario delante.
 *
 * El anexo 04 lo dejó anotado: la bandeja enseñaba el nivel, el título y el
 * teammate, y **nada más** — «sin vista previa, prueba ni antigüedad». Decidir
 * así es decidir por el título, que es justo lo que una aprobación existe para
 * evitar.
 *
 * Y el callejón: sin permiso para decidir sólo salía «Tu rol no puede decidir
 * esto. Pídeselo a un administrador», y **desaparecía también «Ver el hilo»** —
 * o sea, ni decides ni puedes leer de qué va.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

const inboxList = vi.fn(async () => ({ ok: true as const, data: [] as unknown[] }));
const inboxDecide = vi.fn(async (_i?: unknown) => ({ ok: true as const, data: {} }));

vi.mock("../src/app/bridge", () => ({
  bridge: {
    inboxList: () => inboxList(),
    inboxDecide: (input: unknown) => inboxDecide(input),
    on: () => () => {},
  },
}));

const { FeedbackProvider } = await import("../src/app/feedback/provider");
const { Inbox } = await import("../src/app/routes/inbox");

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

const TARJETA = {
  action_id: "a-1",
  task_id: "t-9",
  thread_id: "th-1",
  run_id: "r-1",
  teammate: { id: "tm-1", name: "Sofía" },
  title: "Enviar el presupuesto",
  kind: "send",
  level: "aviso" as const,
  client_ref: "boreal",
  proposed_at: new Date(Date.now() - 45 * 60_000).toISOString(),
  can_decide: true,
  machine: "MacBook de Luis",
  reversible: false,
};

function pendientes(items: unknown[] = [TARJETA]) {
  inboxList.mockResolvedValue({ ok: true, data: items });
  return render(
    <FeedbackProvider>
      <Inbox onOpenThread={() => {}} focus={null} />
    </FeedbackProvider>,
  );
}

describe("qué se hará, sobre qué y desde cuándo (10.1)", () => {
  it("nombra el teammate y el cliente", async () => {
    pendientes();
    const fila = (await screen.findByText("Enviar el presupuesto")).closest("li")!;
    expect(fila.textContent).toMatch(/Sofía/);
    expect(fila.textContent).toMatch(/boreal/);
  });

  it("dice desde cuándo espera, no sólo que espera", async () => {
    pendientes();
    const fila = (await screen.findByText("Enviar el presupuesto")).closest("li")!;
    // Cuarenta y cinco minutos esperando y cinco segundos no son lo mismo.
    expect(fila.textContent).toMatch(/hace|ago/i);
  });

  it("y si toca una máquina, cuál", async () => {
    pendientes();
    const fila = (await screen.findByText("Enviar el presupuesto")).closest("li")!;
    expect(fila.textContent).toMatch(/MacBook de Luis/);
  });

  it("dice si tiene vuelta atrás, que es lo que más pesa al decidir", async () => {
    pendientes();
    const fila = (await screen.findByText("Enviar el presupuesto")).closest("li")!;
    expect(fila.textContent).toMatch(/no se deshace|cannot be undone/i);
  });

  it("y lo reversible también se dice: callarlo deja suponer lo peor", async () => {
    pendientes([{ ...TARJETA, reversible: true }]);
    const fila = (await screen.findByText("Enviar el presupuesto")).closest("li")!;
    expect(fila.textContent).toMatch(/se puede deshacer|can be undone/i);
  });
});

describe("sin permiso para decidir, el hilo sigue alcanzable (10.6)", () => {
  it("se dice a quién pedírselo", async () => {
    pendientes([{ ...TARJETA, can_decide: false }]);
    expect(await screen.findByRole("note")).toBeInTheDocument();
  });

  it("y «Ver el hilo» **no** desaparece: era el callejón del anexo 04", async () => {
    const onOpenThread = vi.fn();
    inboxList.mockResolvedValue({ ok: true, data: [{ ...TARJETA, can_decide: false }] });
    render(
      <FeedbackProvider>
        <Inbox onOpenThread={onOpenThread} focus={null} />
      </FeedbackProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: /ver el hilo|open the thread/i }));
    expect(onOpenThread).toHaveBeenCalledWith("tm-1");
  });
});

describe("la decisión queda atribuida (10.7)", () => {
  it("una ya decidida dice quién y qué decidió", async () => {
    pendientes([
      { ...TARJETA, decided: { decision: "confirm", by: "Luis", at: new Date().toISOString() } },
    ]);
    const fila = (await screen.findByText("Enviar el presupuesto")).closest("li")!;
    expect(fila.textContent).toMatch(/Luis/);
    expect(fila.textContent).toMatch(/aprobó|approved/i);
  });

  it("y ya no ofrece decidir otra vez", async () => {
    pendientes([
      { ...TARJETA, decided: { decision: "cancel", by: "Luis", at: new Date().toISOString() } },
    ]);
    await screen.findByText("Enviar el presupuesto");
    expect(screen.queryByRole("button", { name: /aprobar|approve/i })).toBeNull();
  });
});

describe("la que produjo el aviso se ve y recibe el foco (10.4)", () => {
  it("se marca como la actual", async () => {
    inboxList.mockResolvedValue({ ok: true, data: [TARJETA] });
    render(
      <FeedbackProvider>
        <Inbox onOpenThread={() => {}} focus="a-1" />
      </FeedbackProvider>,
    );
    const fila = (await screen.findByText("Enviar el presupuesto")).closest("li")!;
    expect(fila).toHaveAttribute("aria-current", "true");
  });

  it("y se le lleva el foco, no sólo se colorea el borde", async () => {
    inboxList.mockResolvedValue({ ok: true, data: [TARJETA] });
    render(
      <FeedbackProvider>
        <Inbox onOpenThread={() => {}} focus="a-1" />
      </FeedbackProvider>,
    );
    await screen.findByText("Enviar el presupuesto");
    await waitFor(() => {
      const fila = screen.getByText("Enviar el presupuesto").closest("li")!;
      expect(fila.contains(document.activeElement)).toBe(true);
    });
  });
});
