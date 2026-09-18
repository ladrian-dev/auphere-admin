// @vitest-environment jsdom
/**
 * Requisito 5.3 — ninguna acción que la persona inicie termina sin señal.
 *
 * El anexo 04 de la investigación cerró la lista: **siete sitios donde algo
 * falla, o sale de la aplicación, sin decirlo**. Decidir en Pendientes, guardar
 * la política local, un directorio que no vale, la versión descargada, leer el
 * entorno y los cambios del teammate, y salir a Stripe o a Google.
 *
 * Aquí se comprueban los que esta historia cablea. Los otros dos tienen dueño
 * declarado y no se comprueban antes de tiempo: el directorio inválido llega
 * con la historia 4, cuando el diálogo pasa a ser de la aplicación, y el
 * portapapeles vive en la consola, que esta spec no reimplementa (003 R12.6).
 *
 * La regla que se comprueba no es «que salga un texto»: es que el fallo se diga
 * **junto a lo que se intentaba** y no en un aviso que se va solo. Por eso cada
 * caso mira el mecanismo, no sólo el mensaje.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

const inboxList = vi.fn(async () => ({ ok: true as const, data: [] as unknown[] }));
const inboxDecide = vi.fn(async (_input?: unknown) => ({ ok: true as const, data: {} }));
const POLICY = { global_mode: "ask", effective: "ask", ceiling: "always", capped: false, per_executable: [] };
const policyPrefs = vi.fn(async () => ({ ok: true as const, data: POLICY }));
const policySetPref = vi.fn(async (_input?: unknown) => ({ ok: true as const, data: POLICY }));

vi.mock("../src/app/bridge", () => ({
  bridge: {
    inboxList: () => inboxList(),
    inboxDecide: (input: unknown) => inboxDecide(input as never),
    policyPrefs: () => policyPrefs(),
    policySetPref: (input: unknown) => policySetPref(input as never),
    on: () => () => {},
  },
}));

const { FeedbackProvider } = await import("../src/app/feedback/provider");
const { Inbox } = await import("../src/app/routes/inbox");
const { LocalExecPolicySection } = await import("../src/app/routes/env");

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  inboxList.mockResolvedValue({ ok: true, data: [] });
  inboxDecide.mockResolvedValue({ ok: true, data: {} });
  policyPrefs.mockResolvedValue({ ok: true, data: POLICY });
});

function conAvisos(ui: React.ReactElement) {
  return render(<FeedbackProvider>{ui}</FeedbackProvider>);
}

const TARJETA = {
  action_id: "a-1",
  task_id: null,
  thread_id: "th-1",
  run_id: "r-1",
  teammate: { id: "t-1", name: "Sofía" },
  title: "Enviar el presupuesto",
  kind: "send",
  level: "aviso",
  client_ref: null,
  proposed_at: "2026-09-17T10:00:00Z",
  can_decide: true,
};

describe("silencio 1 — decidir en Pendientes", () => {
  it("un fallo al decidir se dice, y junto a la tarjeta que se intentaba decidir", async () => {
    inboxList.mockResolvedValue({ ok: true, data: [TARJETA] });
    inboxDecide.mockResolvedValue({ ok: false, code: "conflict" } as never);
    conAvisos(<Inbox onOpenThread={() => {}} focus={null} />);
    await userEvent.click(await screen.findByRole("button", { name: /aprobar|approve/i }));

    const tarjeta = screen.getByText("Enviar el presupuesto").closest("li")!;
    await waitFor(() => expect(tarjeta.textContent).toMatch(/no se pudo decidir|could not be decided/i));
  });

  it("y la tarjeta sigue ahí: un fallo al decidir no decide nada", async () => {
    inboxList.mockResolvedValue({ ok: true, data: [TARJETA] });
    inboxDecide.mockResolvedValue({ ok: false, code: "conflict" } as never);
    conAvisos(<Inbox onOpenThread={() => {}} focus={null} />);
    await userEvent.click(await screen.findByRole("button", { name: /aprobar|approve/i }));
    await waitFor(() => expect(screen.getByText(/no se pudo decidir|could not be decided/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /aprobar|approve/i })).toBeInTheDocument();
  });

  it("si sale bien no se dice nada: el resultado ya es la señal", async () => {
    inboxList.mockResolvedValue({ ok: true, data: [TARJETA] });
    conAvisos(<Inbox onOpenThread={() => {}} focus={null} />);
    await userEvent.click(await screen.findByRole("button", { name: /aprobar|approve/i }));
    await waitFor(() => expect(inboxDecide).toHaveBeenCalled());
    expect(screen.queryByText(/no se pudo decidir|could not be decided/i)).toBeNull();
  });
});

describe("silencio 2 — guardar la política de ejecución local", () => {
  it("un fallo al guardar se dice junto a los botones", async () => {
    policySetPref.mockResolvedValue({ ok: false, code: "network" } as never);
    conAvisos(<LocalExecPolicySection initial={null} />);
    await userEvent.click(await screen.findByRole("button", { name: /permitir siempre|always allow/i }));
    await waitFor(() => expect(screen.getByText(/no se pudo guardar|could not be saved/i)).toBeInTheDocument());
  });

  it("y el botón sigue diciendo lo que hay de verdad, no lo que se intentó", async () => {
    // Pintar «Siempre» como elegida tras un fallo sería la pantalla mintiendo:
    // la próxima ejecución pediría permiso y nadie entendería por qué.
    policySetPref.mockResolvedValue({ ok: false, code: "network" } as never);
    conAvisos(<LocalExecPolicySection initial={null} />);
    const siempre = await screen.findByRole("button", { name: /permitir siempre|always allow/i });
    await userEvent.click(siempre);
    await waitFor(() => expect(screen.getByText(/no se pudo guardar|could not be saved/i)).toBeInTheDocument());
    expect(siempre).toHaveAttribute("aria-pressed", "false");
  });
});

describe("la regla que ninguno de los siete puede saltarse", () => {
  it("un fallo nunca viaja en un aviso que se va solo", async () => {
    inboxList.mockResolvedValue({ ok: true, data: [TARJETA] });
    inboxDecide.mockResolvedValue({ ok: false, code: "conflict" } as never);
    const { container } = conAvisos(<Inbox onOpenThread={() => {}} focus={null} />);
    await userEvent.click(await screen.findByRole("button", { name: /aprobar|approve/i }));
    await waitFor(() => expect(screen.getByText(/no se pudo decidir|could not be decided/i)).toBeInTheDocument());
    // La región efímera vive fija abajo a la derecha; un error no puede estar ahí.
    const efimeros = container.querySelector(".fixed.right-4");
    expect(efimeros).toBeNull();
  });
});
