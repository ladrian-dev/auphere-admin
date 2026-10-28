import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";

import { ApiError } from "@/api/errors";
import { keys } from "@/api/query";
import { AgentsGroup } from "@/features/agents/agents-group";
import { t as translate, type T } from "@/i18n/t";
import { agentActions, agentStateLabel, channelStateLabel, confirmRequired, pausedBy, pausedSince, toneOf, whyNoResume } from "@/lib/agents-model";

import { agent, AGENT, CHANNEL, pausedBySystem, Providers, testClient } from "../test/fabrica-fixtures";

/**
 * Spec 047, T169 (requirements 25, 27, 50.1–50.3, 50.5, 50.9): the agents on
 * the phone — their state in the console's words, pausing and resuming an
 * agent and a number, and what the person cannot do said instead of offered.
 */
const t: T = (k, v) => translate("es", k, v);
// Whole screens with a real query cache: a loaded machine running the suite in parallel needs more than 5 s.
jest.setTimeout(15_000);

const mockEndpoints = {
  agents: jest.fn(),
  me: jest.fn(),
  home: jest.fn(async () => ({})),
  pauseAgent: jest.fn(),
  resumeAgent: jest.fn(),
  pauseChannel: jest.fn(),
  resumeChannel: jest.fn(),
};
jest.mock("@/api/endpoints", () => ({ endpoints: new Proxy({}, { get: (_t, k: string) => (mockEndpoints as Record<string, unknown>)[k] }) }));
jest.mock("@/api/reservas", () => ({ demo: null }));
let mockOnline = true;
jest.mock("@/ui/online", () => ({ useOnline: () => mockOnline }));
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ id: "11111111-1111-4111-8111-111111111111" }),
  Stack: { Screen: () => null },
  router: { push: jest.fn(), back: jest.fn() },
}));

const me = { user: { name: "Valeria", email: "v@flor.test" }, client: { name: "Flor y Encanto", modules: ["panel", "agents"] }, nav: ["panel", "agents"], agents: [], channels: [], balance_contact: { kind: "partner", name: "Amacrux" }, business: { timezone: "America/Santiago", hours: null, hours_label: null } };

describe("the state, in the console's words (25.5)", () => {
  it("says each state and each reason of a pause", () => {
    expect(agentStateLabel({ code: "serving", tone: "positive" }, t)).toBe("Atendiendo");
    expect(agentStateLabel({ code: "testing", tone: "info" }, t)).toBe("En prueba");
    expect(agentStateLabel({ code: "ready_no_channel", tone: "info" }, t)).toBe("Listo · sin canal");
    expect(agentStateLabel({ code: "paused", tone: "warn", reason: "no_balance" }, t)).toBe("Pausado · sin saldo");
    expect(agentStateLabel({ code: "paused", tone: "warn", reason: "agent_cap" }, t)).toBe("Pausado · su tope");
    expect(agentStateLabel({ code: "paused", tone: "warn", reason: null }, t)).toBe("Pausado · a mano");
    // A code this version does not know says nothing rather than something wrong.
    expect(agentStateLabel({ code: "flying", tone: "info" }, t)).toBeNull();
  });

  it("a number's state, with its problem", () => {
    expect(channelStateLabel({ code: "everyone", tone: "positive" }, t)).toBe("A todos");
    expect(channelStateLabel({ code: "paused", tone: "warn" }, t)).toBe("En pausa");
    expect(channelStateLabel({ code: "problem", tone: "danger", reason: "auth_expired" }, t)).toBe("Con problemas · hay que volver a autorizar");
  });

  it("the console's tones as the app's", () => {
    expect(toneOf("warn")).toBe("warning");
    expect(toneOf("muted")).toBe("neutral");
    expect(toneOf("positive")).toBe("positive");
  });

  it("who paused it by name, from where, and since when (`paused_by_name`, `paused_at`)", () => {
    expect(pausedBy({ paused_by_kind: "client_user", paused_origin: "app", paused_by_name: "Marta" }, "Amacrux", t)).toBe("Lo pausó Marta desde la app.");
    expect(pausedBy({ paused_by_kind: "client_user", paused_origin: "lite_web", paused_by_name: "Marta" }, "Amacrux", t)).toBe("Lo pausó Marta desde la consola web.");
    expect(pausedBy({ paused_by_kind: "partner_member", paused_origin: "console", paused_by_name: "Luis" }, "Amacrux", t)).toBe("Lo pausó Luis, de Amacrux.");
    const now = new Date("2026-10-28T12:00:00Z");
    expect(pausedSince("2026-10-28T11:55:00Z", now, "es", t)).toBe("En pausa desde hace 5 min.");
    expect(pausedSince("2026-10-28T09:00:00Z", now, "es", t)).toBe("En pausa desde hace 3 h.");
    expect(pausedSince("2026-10-20T09:30:00Z", now, "es", t)).toMatch(/^En pausa desde el 20 de octubre/);
    // The system's pause has no time of a person: nothing is said.
    expect(pausedSince(null, now, "es", t)).toBeNull();
  });

  it("who paused it and from where, without inventing a name", () => {
    expect(pausedBy({ paused_by_kind: "client_user", paused_origin: "app" }, "Amacrux", t)).toBe("Lo pausó una persona de tu equipo desde la app.");
    expect(pausedBy({ paused_by_kind: "partner_member", paused_origin: "console" }, "Amacrux", t)).toBe("Lo pausó Amacrux.");
    expect(pausedBy({ paused_by_kind: "system", paused_origin: "system" }, "Amacrux", t)).toBeNull();
  });

  it("a pause the system put has no «Reanudar», and says why and whom to ask (27.4)", () => {
    expect(agentActions(pausedBySystem("no_balance"))).toEqual({ pause: false, resume: false, blocked: "no_balance" });
    expect(whyNoResume("no_balance", "Amacrux", t)).toMatch(/Pídeselo a Amacrux\.$/);
    expect(agentActions(agent())).toEqual({ pause: true, resume: false, blocked: null });
  });

  it("`confirm_required` is a question with a count, not an error", () => {
    expect(confirmRequired(new ApiError(409, "confirm_required", { open_conversations: 3 }))).toBe(3);
    expect(confirmRequired(new ApiError(409, "not_allowed"))).toBeNull();
  });
});

describe("«Agentes» on Inicio (50.1)", () => {
  it("one row per agent with its state in words, and the way into it", async () => {
    const onAgent = jest.fn();
    await render(<AgentsGroup read={{ state: "ready", items: [agent(), pausedBySystem("agent_cap")] }} onAgent={onAgent} t={t} />);
    expect(screen.getByRole("header", { name: "Agentes" })).toBeTruthy();
    const row = screen.getAllByRole("button", { name: /^Recepción\. / });
    expect(row[0]!.props.accessibilityLabel).toBe("Recepción. Atendiendo");
    expect(row[1]!.props.accessibilityLabel).toBe("Recepción. Pausado · su tope");
    await fireEvent.press(row[0]!);
    expect(onAgent).toHaveBeenCalledWith(AGENT);
  });

  it("failed: says so, with a retry; none: says who creates them", async () => {
    const retry = jest.fn();
    await render(<AgentsGroup read={{ state: "error", retry }} onAgent={jest.fn()} t={t} />);
    await fireEvent.press(screen.getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalled();
    await render(<AgentsGroup read={{ state: "ready", items: [] }} onAgent={jest.fn()} t={t} />);
    expect(screen.getByText(/Los crea quien gestiona tu negocio en Auphere/)).toBeTruthy();
  });
});

describe("Agentes › un agente (T169, 27, 50.2)", () => {
  const AgentScreen = require("@/app/agente/[id]").default as () => React.JSX.Element;

  async function open(cards = [agent()]) {
    mockEndpoints.agents.mockResolvedValue({ items: cards });
    mockEndpoints.me.mockResolvedValue(me);
    const client = testClient();
    client.setQueryData(keys.agents, { items: cards });
    client.setQueryData(keys.me, me);
    await render(
      <Providers client={client}>
        <AgentScreen />
      </Providers>,
    );
    return client;
  }

  beforeEach(() => {
    mockOnline = true;
    for (const f of Object.values(mockEndpoints)) f.mockReset();
    mockEndpoints.home.mockResolvedValue({});
  });

  it("says its state, what it means and its numbers; «Pausar» pauses at once without conversations in progress (27.8)", async () => {
    await open();
    expect(screen.getByText("Atendiendo")).toBeTruthy();
    expect(screen.getByText("Responde a todos los que escriben a sus números.")).toBeTruthy();
    expect(screen.getByText("WhatsApp · +56 9 5555 0101")).toBeTruthy();
    mockEndpoints.pauseAgent.mockResolvedValue(agent({ visible_state: { code: "paused", tone: "warn", reason: "manual" }, pause_reason: "manual", paused_by_kind: "client_user", paused_origin: "app", allowed: ["resume"] }));
    mockEndpoints.agents.mockResolvedValue({ items: [agent({ visible_state: { code: "paused", tone: "warn", reason: "manual" }, pause_reason: "manual", paused_by_kind: "client_user", paused_origin: "app", allowed: ["resume"] })] });
    await fireEvent.press(screen.getByRole("button", { name: "Pausar" }));
    expect(mockEndpoints.pauseAgent).toHaveBeenCalledWith(AGENT, false);
    await waitFor(() => expect(screen.getByText("Pausado · a mano")).toBeTruthy());
    expect(screen.getByTestId("agent-paused-by").props.children).toBe("Lo pausó una persona de tu equipo desde la app.");
    expect(screen.getByText("Recepción está en pausa. Los mensajes se guardan y van a la Bandeja.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reanudar" })).toBeTruthy();
  });

  it("with conversations in progress it asks first and says how many; confirming pauses (27.8)", async () => {
    const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
    await open([agent({ open_conversations: 2 })]);
    expect(screen.getByText("2 conversaciones en curso")).toBeTruthy();
    mockEndpoints.pauseAgent.mockRejectedValueOnce(new ApiError(409, "confirm_required", { open_conversations: 2 }));
    await fireEvent.press(screen.getByRole("button", { name: "Pausar" }));
    expect(alert).toHaveBeenCalledWith(
      "¿Pausar Recepción?",
      "Hay 2 conversaciones en curso. Dejará de responder en todas, y los mensajes nuevos irán a la Bandeja.",
      expect.any(Array),
    );
    mockEndpoints.pauseAgent.mockResolvedValue(agent({ visible_state: { code: "paused", tone: "warn", reason: "manual" }, allowed: ["resume"] }));
    const buttons = alert.mock.calls[0]![2] as { text: string; onPress?: () => void }[];
    await act(async () => buttons.find((b) => b.text === "Pausar igualmente")!.onPress!());
    expect(mockEndpoints.pauseAgent).toHaveBeenLastCalledWith(AGENT, true);
    alert.mockRestore();
  });

  it("paused for lack of balance: no button, the reason, and whom to ask (27.4)", async () => {
    await open([pausedBySystem("no_balance")]);
    expect(screen.getByText("Pausado · sin saldo")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reanudar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Pausar" })).toBeNull();
    expect(screen.getByTestId("agent-why").props.children).toMatch(/vuelve a responder solo en cuanto haya más\. Pídeselo a Amacrux\./);
  });

  it("«Reanudar» resumes a pause of a person; a 409 `system_pause` says why", async () => {
    const paused = agent({
      visible_state: { code: "paused", tone: "warn", reason: "manual" },
      pause_reason: "manual",
      paused_by_kind: "client_user",
      paused_origin: "app",
      paused_by_name: "Marta",
      paused_at: new Date(Date.now() - 5 * 60_000).toISOString(),
      allowed: ["resume"],
    });
    await open([paused]);
    expect(screen.getByTestId("agent-paused-by").props.children).toBe("Lo pausó Marta desde la app. En pausa desde hace 5 min.");
    mockEndpoints.resumeAgent.mockRejectedValueOnce(new ApiError(409, "system_pause", { pause_reason: "agent_cap" }));
    await fireEvent.press(screen.getByRole("button", { name: "Reanudar" }));
    expect(mockEndpoints.resumeAgent).toHaveBeenCalledWith(AGENT);
    expect(await screen.findByText(/Llegó a su tope de gasto del mes/)).toBeTruthy();
  });

  it("a number pauses on its own, named for the screen reader", async () => {
    await open();
    const paused = { id: CHANNEL, type: "whatsapp", identifier: "+56 9 5555 0101", visible_state: { code: "paused", tone: "warn" }, allowed: ["resume" as const] };
    mockEndpoints.pauseChannel.mockResolvedValue(paused);
    // The list read again after the write says the same as the write.
    mockEndpoints.agents.mockResolvedValue({ items: [agent({ channels: [paused] })] });
    await fireEvent.press(screen.getByRole("button", { name: "Pausar el número +56 9 5555 0101" }));
    expect(mockEndpoints.pauseChannel).toHaveBeenCalledWith(CHANNEL);
    expect(await screen.findByText("En pausa")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reanudar el número +56 9 5555 0101" })).toBeTruthy();
  });

  it("offline: says a connection is needed, and nothing is sent (50.5)", async () => {
    mockOnline = false;
    await open();
    expect(screen.getByText("Sin conexión: conéctate para pausar o reanudar.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Pausar" }).props.accessibilityState).toMatchObject({ disabled: true });
    expect(screen.getByRole("button", { name: "Pausar el número +56 9 5555 0101" }).props.accessibilityState).toMatchObject({ disabled: true });
    await fireEvent.press(screen.getByRole("button", { name: "Pausar" }));
    expect(mockEndpoints.pauseAgent).not.toHaveBeenCalled();
  });

  it("what the person cannot do is said once, never a button that refuses (50.3)", async () => {
    await open();
    expect(screen.getByText("Desde aquí puedes pausar y reanudar. Crear agentes, cambiar lo que dicen o conectar números lo hace Amacrux.")).toBeTruthy();
    for (const word of ["Archivar", "Publicar", "Conectar", "Renombrar"]) expect(screen.queryByRole("button", { name: new RegExp(word) })).toBeNull();
  });

  it("an agent that is no longer in the list says so", async () => {
    await open([]);
    expect(screen.getByText("Este agente ya no está")).toBeTruthy();
  });
});
