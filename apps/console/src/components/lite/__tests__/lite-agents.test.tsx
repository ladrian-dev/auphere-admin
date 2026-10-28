import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { LiteAgent, LiteAgentChannel, LiteAgents } from "@/lib/backend/lite-agents";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/agentes/actions", () => ({}));

const { LiteAgentsView } = await import("../lite-agents");
const { pauseLine } = await import("../lite-agents-model");
type Actions = NonNullable<React.ComponentProps<typeof LiteAgentsView>["actions"]>;

/**
 * Spec 047 (T168; requisitos 50.1, 50.2 y 27) — «Agentes» de la consola lite:
 * el estado de cada agente con los textos de toda la consola, sus números,
 * pausar con confirmación (y la cifra de conversaciones en curso), reanudar, y
 * una pausa del sistema que se explica sin botón.
 */

const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const VENTAS = "00000000-0000-4000-8000-0000000000a3";
const CH1 = "00000000-0000-4000-8000-0000000000c1";

function channel(over: Partial<LiteAgentChannel> = {}): LiteAgentChannel {
  return { id: CH1, type: "whatsapp", identifier: "+34 611 20 48 93", visible_state: { code: "everyone", tone: "positive", reason: null }, allowed: ["pause"], ...over };
}

function agent(over: Partial<LiteAgent> = {}): LiteAgent {
  return {
    id: RECEPCION,
    name: "Recepción",
    is_default: true,
    visible_state: { code: "serving", tone: "positive", reason: null },
    pause_reason: null,
    paused_by_kind: null,
    paused_origin: null,
    open_conversations: 0,
    channels: [channel()],
    allowed: ["pause"],
    ...over,
  };
}

const ok = <T,>(data: T) => ({ ok: true as const, data });
const fail = (status: number, code: string, info: Record<string, unknown> = {}) => ({ ok: false as const, status, message: code, code, info });

function view(data: LiteAgents | null, over: Partial<Actions> = {}) {
  const actions: Actions = {
    reload: vi.fn(async () => ok({ items: [agent()] })),
    pauseAgent: vi.fn(async () => ok(agent({ visible_state: { code: "paused", tone: "warn", reason: "manual" }, pause_reason: "manual", paused_by_kind: "client_user", paused_origin: "lite_web", allowed: ["resume"] }))),
    resumeAgent: vi.fn(async () => ok(agent())),
    pauseChannel: vi.fn(async () => ok(channel({ visible_state: { code: "paused", tone: "warn", reason: null }, allowed: ["resume"] }))),
    resumeChannel: vi.fn(async () => ok(channel())),
    ...over,
  };
  const r = render(
    <LocaleProvider locale="es">
      <LiteAgentsView initial={data} actions={actions} />
    </LocaleProvider>,
  );
  return { ...r, actions };
}

describe("«Agentes» de la consola lite (T168)", { timeout: 30_000 }, () => {
  it("pinta cada agente con su estado, sus números y lo que se puede hacer, y pasa axe", async () => {
    const { container } = view({ items: [agent()] });
    const card = screen.getByRole("region", { name: "Recepción" });
    expect(within(card).getByText("Atendiendo")).toBeInTheDocument();
    expect(within(card).getByText("Principal")).toBeInTheDocument();
    const numbers = within(card).getByRole("list", { name: "Números de Recepción" });
    expect(within(numbers).getByText("+34 611 20 48 93")).toBeInTheDocument();
    expect(within(numbers).getByText("A todos")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Pausar" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Pausar el número" })).toBeInTheDocument();
    // Nada de lo que es del partner (50.3).
    expect(screen.queryByRole("button", { name: /Archivar|Publicar|Nuevo agente/ })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("pausar siempre se confirma y dice cuántas conversaciones pasan a la Bandeja", async () => {
    const user = userEvent.setup();
    const { actions } = view({ items: [agent({ open_conversations: 3 })] });
    await user.click(screen.getByRole("button", { name: "Pausar" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Pausar Recepción?" });
    expect(within(dialog).getByText(/Tiene 3 conversaciones en curso/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Pausar el agente" }));
    await waitFor(() => expect(actions.pauseAgent).toHaveBeenCalledWith({ id: RECEPCION, confirm: true }));
    expect(await screen.findByText("Pausado · a mano")).toBeInTheDocument();
    expect(screen.getByText("Lo pausó alguien de tu equipo desde la web.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reanudar" })).toBeInTheDocument();
    // El aviso lleva su acción (47.6).
    expect(toast.success).toHaveBeenCalledWith("Recepción está en pausa. Los mensajes van a la Bandeja.", expect.objectContaining({ action: expect.objectContaining({ label: "Reanudar" }) }));
  });

  it("si empezaron conversaciones desde que se leyó la lista, vuelve a preguntar con la cifra de ahora", async () => {
    const user = userEvent.setup();
    const pauseAgent = vi.fn().mockResolvedValueOnce(fail(409, "confirm_required", { open_conversations: 2 })).mockResolvedValueOnce(ok(agent({ visible_state: { code: "paused", tone: "warn", reason: "manual" }, allowed: ["resume"] })));
    view({ items: [agent()] }, { pauseAgent });
    await user.click(screen.getByRole("button", { name: "Pausar" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Pausar el agente" }));
    expect(pauseAgent).toHaveBeenNthCalledWith(1, { id: RECEPCION, confirm: false });
    const again = await screen.findByText(/Tiene 2 conversaciones en curso/);
    await user.click(within(again.closest("[role=dialog]") as HTMLElement).getByRole("button", { name: "Pausar el agente" }));
    await waitFor(() => expect(pauseAgent).toHaveBeenNthCalledWith(2, { id: RECEPCION, confirm: true }));
  });

  it("una pausa del sistema se explica y no ofrece «Reanudar» (§V)", () => {
    view({ items: [agent({ visible_state: { code: "paused", tone: "warn", reason: "no_balance" }, pause_reason: "no_balance", allowed: [] })] });
    expect(screen.getByText("Pausado · sin saldo")).toBeInTheDocument();
    expect(screen.getByText(/Vuelve a atender solo en cuanto haya saldo/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reanudar" })).toBeNull();
  });

  it("reanudar un número en pausa; con más de dos botones en la lista, cada fila los pliega en «⋯»", async () => {
    const user = userEvent.setup();
    const paused = channel({ visible_state: { code: "paused", tone: "warn", reason: null }, allowed: ["resume"] });
    const { actions } = view({
      items: [agent({ channels: [paused] }), agent({ id: VENTAS, name: "Ventas", is_default: false, channels: [] }), agent({ id: "00000000-0000-4000-8000-0000000000a4", name: "Citas", is_default: false, channels: [] })],
    });
    // Tres agentes con un botón cada uno: la regla de los tres puntos.
    expect(screen.getAllByRole("button", { name: /^Acciones de / })).toHaveLength(3);
    await user.click(screen.getByRole("button", { name: "Reanudar el número" }));
    await waitFor(() => expect(actions.resumeChannel).toHaveBeenCalledWith({ id: CH1 }));
    expect(await screen.findByText("A todos")).toBeInTheDocument();
  });

  it("sin agentes dice quién los crea; si la lista no llega, deja reintentar", async () => {
    const user = userEvent.setup();
    const { unmount } = view({ items: [] });
    expect(screen.getByText("Aún no tienes agentes")).toBeInTheDocument();
    unmount();
    const { actions } = view(null);
    expect(screen.getByText("No pudimos leer tus agentes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(actions.reload).toHaveBeenCalled());
    expect(await screen.findByRole("region", { name: "Recepción" })).toBeInTheDocument();
  });

  it("un «no» del sistema llega en palabras", async () => {
    const user = userEvent.setup();
    view({ items: [agent({ visible_state: { code: "paused", tone: "warn", reason: "manual" }, pause_reason: "manual", allowed: ["resume"] })] }, { resumeAgent: vi.fn(async () => fail(409, "system_pause")) });
    await user.click(screen.getByRole("button", { name: "Reanudar" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Esta pausa la puso el sistema. Se quita sola cuando se arregla lo que la causó."));
  });
});

describe("pauseLine", () => {
  const base = { visible_state: { code: "paused", tone: "warn", reason: "manual" }, pause_reason: "manual", paused_by_kind: "client_user", paused_origin: "app" };
  it("quién y desde dónde, o cuándo vuelve una pausa del sistema", () => {
    expect(pauseLine(base)?.key).toBe("lite.agents.pausedBy.app");
    expect(pauseLine({ ...base, paused_origin: "lite_web" })?.key).toBe("lite.agents.pausedBy.web");
    expect(pauseLine({ ...base, paused_by_kind: "partner_user" })?.key).toBe("lite.agents.pausedBy.partner");
    expect(pauseLine({ ...base, pause_reason: "agent_cap" })?.key).toBe("lite.agents.system.agent_cap");
    expect(pauseLine({ ...base, pause_reason: "client_paused" })?.key).toBe("lite.agents.system.client_paused");
    expect(pauseLine({ ...base, visible_state: { code: "serving", tone: "positive", reason: null } })).toBeNull();
  });

  it("dice el nombre de quien lo pausó cuando la API lo trae (27.6)", () => {
    expect(pauseLine({ ...base, paused_by_name: "Marta" })).toEqual({ key: "lite.agents.pausedBy.appNamed", name: "Marta" });
    expect(pauseLine({ ...base, paused_origin: "lite_web", paused_by_name: "Marta" })).toEqual({ key: "lite.agents.pausedBy.webNamed", name: "Marta" });
    expect(pauseLine({ ...base, paused_by_name: "  " })).toEqual({ key: "lite.agents.pausedBy.app", name: null });
    // La de otra persona del partner nunca lleva nombre en la lite.
    expect(pauseLine({ ...base, paused_by_kind: "partner_user", paused_by_name: "Luis" })).toEqual({ key: "lite.agents.pausedBy.partner", name: null });
  });
});
