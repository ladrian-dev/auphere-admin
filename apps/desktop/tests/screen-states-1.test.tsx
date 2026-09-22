// @vitest-environment jsdom
/**
 * Requisitos 4.1 y 4.9 — el inventario de estados, parte 1: Hoy, la lista
 * lateral, Pendientes y Cuenta.
 *
 * La tabla de `data-model.md` §5 existe para que «la pantalla no miente» sea
 * comprobable en vez de opinable. Cada celda es un caso; aquí se recorren los
 * de estas cuatro pantallas, con una regla por encima de todas:
 *
 * > **cargando y vacío no pueden verse igual.**
 *
 * Es el error que se vio en la aplicación instalada el 2026-09-17: mientras el
 * equipo cargaba, la lista lateral no enseñaba nada — exactamente lo mismo que
 * enseña cuando de verdad no tienes teammates.
 *
 * Dos celdas de la tabla **no** se comprueban aquí, a propósito, porque sus
 * tareas están en otras historias y un test en rojo durante tres fases no es
 * test primero, es un test roto: el fallo al decidir en Pendientes (historia 3,
 * T072) y «plan sin capacidad» en Hoy y Cuenta (historia 5, T106-T117).
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

const inboxList = vi.fn();
const inboxDecide = vi.fn(async () => ({ ok: true as const, data: {} }));
const on = vi.fn(() => () => {});

vi.mock("../src/app/bridge", () => ({
  bridge: { inboxList: () => inboxList(), inboxDecide: () => inboxDecide(), on: () => on() },
}));

const { FeedbackProvider } = await import("../src/app/feedback/provider");
const { Today } = await import("../src/app/routes/today");
const { Inbox } = await import("../src/app/routes/inbox");
const { Sidebar } = await import("../src/app/shell/sidebar");
const { Account } = await import("../src/app/routes/account");

afterEach(cleanup);
beforeEach(() => {
  inboxList.mockReset();
  on.mockReset();
  on.mockReturnValue(() => {});
});

const HOY = {
  workstation: null,
  onOpenWorkstation: () => {},
  waiting: 0,
  teammates: [],
  onRetry: () => {},
  onOpenPending: () => {},
  onCreate: () => {},
  onOpenTeammate: () => {},
  // Spec 013, R6 — escribir desde Hoy. Con `teammates: []` no se pinta el
  // composer, que es justo lo que estos tres estados comprueban.
  onStart: () => {},
};

const LATERAL = {
  active: "hoy" as const,
  onSelect: () => {},
  permissions: [] as string[],
  waiting: 0,
  teammates: [] as Array<{ id: string; name: string; unread: boolean }>,
  selectedTeammate: null,
  onSelectTeammate: () => {},
};

const PRESUPUESTO = {
  used: 10,
  cap: 100,
  remaining: 90,
  percent: 10,
  exhausted: false,
  period: "2026-09",
  resets_at: "2026-10-01T00:00:00Z",
};

const CUENTA = {
  usage: { budget: PRESUPUESTO, by_teammate: [] },
  team: { members: [] },
  policy: null,
  onRetry: () => {},
  onOpenConsole: () => {},
};

/** Pendientes avisa por la taxonomía, así que necesita su proveedor. */
function pendientes() {
  return render(
    <FeedbackProvider>
      <Inbox onOpenThread={() => {}} focus={null} />
    </FeedbackProvider>,
  );
}

/** El texto visible de la pantalla, para poder comparar dos estados enteros. */
function visible(el: HTMLElement): string {
  return (el.textContent ?? "").replace(/\s+/g, " ").trim();
}

describe("Hoy — cargando, vacío y error son tres pantallas distintas", () => {
  it("cargando lo dice, y no se parece al vacío", () => {
    const { container: cargando } = render(<Today {...HOY} status="loading" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    const texto = visible(cargando);
    cleanup();
    const { container: vacio } = render(<Today {...HOY} status="ready" />);
    expect(visible(vacio)).not.toBe(texto);
  });

  it("el vacío de primer uso dice qué hacer, y deja hacerlo", () => {
    render(<Today {...HOY} status="ready" />);
    expect(screen.getByRole("button", { name: /crear|create/i })).toBeInTheDocument();
  });

  it("el error trae reintento y no se lleva por delante el resto de la pantalla", () => {
    render(<Today {...HOY} status="error" />);
    expect(screen.getByRole("button", { name: /reintentar|retry/i })).toBeInTheDocument();
    // «error por tarjeta, el resto vive»: lo que te espera sigue en pie.
    expect(screen.getByRole("heading", { name: /espera|waiting/i })).toBeInTheDocument();
  });

  it("sin permiso no se ofrece un control apagado, se dice a quién pedirlo (4.9)", () => {
    render(<Today {...HOY} status="forbidden" />);
    expect(screen.queryByRole("button", { name: /crear|create/i })).toBeNull();
  });
});

describe("Lista lateral — lo que el 2026-09-17 se vio mal", () => {
  it("mientras carga el equipo lo dice, en vez de parecer que no tienes ninguno", () => {
    const { container } = render(<Sidebar {...LATERAL} rosterStatus="loading" />);
    expect(within(container).getByRole("status")).toBeInTheDocument();
  });

  it("y sin teammates ofrece crear el primero, no un hueco", async () => {
    const onCreate = vi.fn();
    render(<Sidebar {...LATERAL} rosterStatus="empty" onCreateTeammate={onCreate} />);
    await userEvent.click(screen.getByRole("button", { name: /crear|create/i }));
    expect(onCreate).toHaveBeenCalledOnce();
  });

  it("si el equipo no se pudo leer, se dice y se puede reintentar", async () => {
    const onRetry = vi.fn();
    render(<Sidebar {...LATERAL} rosterStatus="error" onRetryRoster={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /reintentar|retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("los tres estados se ven distintos entre sí", () => {
    const textos = new Set<string>();
    for (const estado of ["loading", "empty", "error"] as const) {
      cleanup();
      const { container } = render(<Sidebar {...LATERAL} rosterStatus={estado} />);
      textos.add(visible(container));
    }
    expect(textos.size).toBe(3);
  });
});

describe("Pendientes — y la lista que se quedó vieja", () => {
  it("cargando no es «nada te espera»", async () => {
    inboxList.mockReturnValue(new Promise(() => {}));
    const { container } = pendientes();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it("vacío dice que nada te espera", async () => {
    inboxList.mockResolvedValue({ ok: true, data: [] });
    pendientes();
    expect(await screen.findByText(/nada te espera|nothing is waiting/i)).toBeInTheDocument();
  });

  it("error de primera carga: motivo y reintento", async () => {
    inboxList.mockResolvedValue({ ok: false, code: "network" });
    pendientes();
    expect(await screen.findByRole("button", { name: /reintentar|retry/i })).toBeInTheDocument();
  });

  it("si la lista ya estaba y el refresco falla, se avisa de que puede estar desfasada", async () => {
    // Es el estado `parcial` de la tabla. Hoy la pantalla se quedaba con la
    // lista vieja sin decir nada: la gente decide sobre algo que quizá ya no
    // existe, y eso es peor que un error.
    inboxList.mockResolvedValueOnce({
      ok: true,
      data: [
        {
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
        },
      ],
    });
    pendientes();
    await screen.findByText("Enviar el presupuesto");

    inboxList.mockResolvedValue({ ok: false, code: "network" });
    await userEvent.click(screen.getByRole("button", { name: /actualizar|refresh/i }));
    await waitFor(() => expect(screen.getByText(/desfasada|out of date/i)).toBeInTheDocument());
    // Y lo que ya estaba **sigue ahí**: el aviso acota, no borra.
    expect(screen.getByText("Enviar el presupuesto")).toBeInTheDocument();
  });

  it("una tarjeta que este rol no decide se muestra y dice a quién pedirlo", async () => {
    inboxList.mockResolvedValue({
      ok: true,
      data: [
        {
          action_id: "a-2",
          task_id: null,
          thread_id: "th-1",
          run_id: "r-1",
          teammate: { id: "t-1", name: "Sofía" },
          title: "Borrar la base",
          kind: "delete",
          level: "critico",
          client_ref: null,
          proposed_at: "2026-09-17T10:00:00Z",
          can_decide: false,
        },
      ],
    });
    pendientes();
    expect(await screen.findByRole("note")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /aprobar|approve/i })).toBeNull();
  });
});

describe("Cuenta — las cuatro celdas que ya existen", () => {
  it("cargando se anuncia y no enseña cifras a medias", () => {
    render(<Account {...CUENTA} status="loading" usage={null} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("meter")).toBeNull();
  });

  it("sin consumo aún se dice, y no se pinta como error", () => {
    render(<Account {...CUENTA} status="ready" />);
    expect(screen.getByRole("meter")).toBeInTheDocument();
    expect(screen.getByText(/todavía|yet|aún/i)).toBeInTheDocument();
  });

  it("error con reintento", async () => {
    const onRetry = vi.fn();
    render(<Account {...CUENTA} status="error" usage={null} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /reintentar|retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("parcial: el equipo ilegible no tumba el consumo", () => {
    render(<Account {...CUENTA} status="ready" team={null} />);
    expect(screen.getByRole("meter")).toBeInTheDocument();
    expect(screen.getByText(/no se pudo leer|could not be read/i)).toBeInTheDocument();
  });
});
