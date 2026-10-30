import { fireEvent, render, screen } from "@testing-library/react-native";

import type { Conversation, Home, Me, UsageSummary } from "@/api/endpoints";
import { redirectSystemPath } from "@/app/+native-intent";
import { ConversationRow } from "@/features/inbox/list/conversation-row";
import { attendsLine, composerMode, waitingReasonText } from "@/features/inbox/model";
import { ControlCard } from "@/features/inbox/thread/control";
import { groupsFor, permissionLines } from "@/features/notices";
import { HomeView } from "@/features/home/home-view";
import { UsageView } from "@/features/usage/usage-view";
import { t as translate, type T } from "@/i18n/t";
import { formatMoney } from "@/lib/format";
import { conversationOf, routeFor } from "@/push/routing";

import { agent, AGENT, CHANNEL, CONVERSATION } from "../test/fabrica-fixtures";

/**
 * Spec 047, T170 (50.6, 50.7, `events.md` §3.1) and the money of T169's
 * Inicio and Consumo: each new notice opens its screen; the Bandeja says who
 * takes a conversation and why it waits; Consumo says the bag's state and
 * whom to ask, in the bag's currency.
 */
const t: T = (k, v) => translate("es", k, v);
// Whole screens with a real query cache: a loaded machine running the suite in parallel needs more than 5 s.
jest.setTimeout(15_000);

describe("the new notices open their screen (50.6)", () => {
  it("`agents.state` opens its agent (a number's, on its agent); the bag's go as `client.balance` to Consumo", () => {
    expect(routeFor({ url: `auphere-customers://agents/${AGENT}`, kind: "agents.state" })).toBe(`/agente/${AGENT}`);
    expect(routeFor({ url: `auphere-customers://agents/${AGENT}/channels/${CHANNEL}`, kind: "agents.state" })).toBe(`/agente/${AGENT}`);
    expect(routeFor({ url: "auphere-customers://usage", kind: "client.balance" })).toBe("/consumo");
    expect(routeFor({ url: `auphere-customers://inbox/${CONVERSATION}`, kind: "inbox.waiting" })).toBe(`/conversacion/${CONVERSATION}`);
    expect(conversationOf({ url: `auphere-customers://agents/${AGENT}` })).toBeNull();
  });

  it("without a URL, or with one it does not know, nothing opens", () => {
    expect(routeFor({ kind: "agents.state", agent_id: AGENT })).toBeNull();
    expect(routeFor({ url: "auphere-customers://agents/../../ajustes", kind: "agents.state" })).toBeNull();
    expect(routeFor({ url: `auphere-customers://agents/${AGENT}/ajustes` })).toBeNull();
  });

  it("a link to an agent opened with the app closed lands on it", () => {
    expect(redirectSystemPath({ path: `auphere-customers://agents/${AGENT}`, initial: true })).toBe(`/agente/${AGENT}`);
    expect(redirectSystemPath({ path: "auphere-customers://agents/nada", initial: true })).toBe("/");
  });

  it("«Agentes y números» is a kind of this phone's notices, only with the module, in its own group", () => {
    expect(groupsFor(["panel", "inbox"]).map((g) => g.group)).toEqual(["inbox", "balance"]);
    const agents = groupsFor(["panel", "inbox", "agents"]).find((g) => g.group === "agents");
    expect(agents?.kinds.map((k) => k.kind)).toEqual(["agents.state"]);
    expect(t(agents!.label)).toBe("Agentes");
    expect(permissionLines(["agents"]).map((l) => l.key)).toContain("agents.state");
  });
});

describe("the Bandeja says who takes it and why it waits (50.7)", () => {
  const conv = (over: Partial<Conversation>): Conversation =>
    ({
      id: CONVERSATION,
      state: "waiting",
      assignee: null,
      agent: null,
      channel: { kind: "whatsapp" },
      contact: { name: "Ana López", handle: "+56 9 1111 2222", initials: "AL", has_avatar: false },
      last_message: { at: "2026-10-28T11:00:00Z", author: { kind: "contact", name: null, is_me: false }, preview: "¿Abren mañana?", has_media: false },
      unread: true,
      tags: [],
      handled_by_agent: { id: AGENT, name: "Recepción" },
      waiting_reason: "paused_agent",
      ...over,
    }) as Conversation;

  it("the reason from its code, and «La atiende {agente}»", async () => {
    await render(<ConversationRow c={conv({})} now={new Date("2026-10-28T12:00:00Z")} t={t} locale="es" agentName={null} onPress={jest.fn()} />);
    expect(screen.getByText("Agente en pausa")).toBeTruthy();
    expect(screen.getByText("La atiende Recepción")).toBeTruthy();
    expect(screen.getByRole("button").props.accessibilityLabel).toMatch(/Necesita humano\. Agente en pausa\. La atiende Recepción\./);
  });

  it("a person who took it is not said to be the agent's", async () => {
    await render(
      <ConversationRow c={conv({ state: "person", assignee: { kind: "member", name: "Luis", is_me: false }, waiting_reason: null })} now={new Date()} t={t} locale="es" agentName={null} onPress={jest.fn()} />,
    );
    expect(screen.queryByText("La atiende Recepción")).toBeNull();
  });

  it("every code of `events.md` §2 in words; an unknown one says nothing", () => {
    expect(waitingReasonText("no_balance", t)).toBe("Sin saldo");
    expect(waitingReasonText("escalated", t)).toBe("Pidió una persona");
    expect(waitingReasonText("reception_loop", t)).toBe("Derivaciones en bucle");
    expect(waitingReasonText("nuevo", t)).toBeNull();
    expect(attendsLine({ state: "agent", assignee: null, agent: null, handled_by_agent: { name: "Ventas" } }, t)).toBe(t("app.inbox.attends.agent", { agent: "Ventas" }));
  });
});

describe("the conversation says why it waits, by its code (50.7, `waiting_code`)", () => {
  const base = { state: "waiting" as const, assignee: null, window: { open: true, closes_at: null }, channel: { kind: "whatsapp", connected: true } };

  it("the code goes with the agent's own words; without a code, as before", () => {
    expect(composerMode({ ...base, waiting_reason: "Pide hablar con alguien", waiting_code: "escalated" })).toMatchObject({ kind: "waiting", code: "escalated", reason: "Pide hablar con alguien" });
    expect(composerMode({ ...base, waiting_reason: null })).toEqual({ kind: "waiting", reason: null, since: null, agent: null });
  });

  it("a pause says so — never «El agente no dijo por qué»", async () => {
    await render(<ControlCard mode={{ kind: "waiting", reason: null, code: "paused_agent" }} busy={false} online t={t} onTakeOver={jest.fn()} onGiveBack={jest.fn()} onReopen={jest.fn()} />);
    expect(screen.getByTestId("waiting-code").props.children).toBe("Agente en pausa");
    expect(screen.queryByText("El agente no dijo por qué.")).toBeNull();
    expect(screen.getByRole("button", { name: "Tomar el control" })).toBeTruthy();
  });

  it("an escalation shows both: why, and what the agent said", async () => {
    await render(<ControlCard mode={{ kind: "waiting", reason: "Pide hablar con alguien", code: "escalated" }} busy={false} online t={t} onTakeOver={jest.fn()} onGiveBack={jest.fn()} onReopen={jest.fn()} />);
    expect(screen.getByTestId("waiting-code").props.children).toBe("Pidió una persona");
    expect(screen.getByTestId("waiting-reason").props.children).toBe("Pide hablar con alguien");
  });
});

describe("Inicio: «Agentes» and the way into Negocio (50.1)", () => {
  const me = { client: { name: "Flor y Encanto", modules: [] }, nav: ["panel", "inbox", "agents", "business"], balance_contact: { kind: "partner", name: "Amacrux" } } as unknown as Me;
  const home = { spend_month: null, conversations: null, waiting: null, balance: null, attention: [], errors: [] } as unknown as Home;

  it("the agents after what needs a person, and Negocio with what the agent will say of the hours", async () => {
    const onAgent = jest.fn();
    const onBusiness = jest.fn();
    await render(
      <HomeView
        me={me}
        home={home}
        t={t}
        locale="es"
        onRetry={jest.fn()}
        onAttend={jest.fn()}
        onUsage={jest.fn()}
        agents={{ state: "ready", items: [agent()] }}
        onAgent={onAgent}
        onBusiness={onBusiness}
        businessHint="De lunes a viernes de 9:00 a 14:00"
      />,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Recepción. Atendiendo" }));
    expect(onAgent).toHaveBeenCalledWith(AGENT);
    await fireEvent.press(screen.getByRole("button", { name: "Horario, servicios y sedes. De lunes a viernes de 9:00 a 14:00" }));
    expect(onBusiness).toHaveBeenCalled();
  });

  it("without the modules, neither", async () => {
    await render(<HomeView me={me} home={home} t={t} locale="es" onRetry={jest.fn()} onAttend={jest.fn()} onUsage={jest.fn()} />);
    expect(screen.queryByText("Agentes")).toBeNull();
    expect(screen.queryByText("Horario, servicios y sedes")).toBeNull();
  });
});

describe("Consumo: the bag's state and whom to ask (50.6, `events.md` §1.4)", () => {
  const summary = (over: Partial<UsageSummary>): UsageSummary => ({
    balance: { assigned: true, remaining_cents: 120000, cap_cents: 1000000, days_left: 4, month_days_left: 10, currency: "EUR" },
    month: { spent_cents: 5000, projection_cents: 9000, conversations: 40, avg_per_conversation_cents: 125 },
    by_agent: null,
    errors: [],
    bag_state: "low",
    days_left: 4,
    partner_name: "Amacrux",
    ...over,
  });
  const view = (s: UsageSummary) =>
    render(
      <UsageView
        summary={s}
        spend={null}
        spendFailed={false}
        anySpend={false}
        days={30}
        onDays={jest.fn()}
        agents={[]}
        agent={null}
        onAgent={jest.fn()}
        t={t}
        locale="es"
        now={new Date("2026-10-21T12:00:00Z")}
        onRetry={jest.fn()}
        onWeb={jest.fn()}
        contact={{ kind: "partner", name: "Amacrux" }}
      />,
    );

  it("«Queda poco», the days at the 7-day pace and «Pídeselo a {partner}» — no button to ask", async () => {
    await view(summary({}));
    expect(screen.getByText("Queda poco")).toBeTruthy();
    expect(screen.getByText("Unos 4 días al ritmo de los últimos 7 días.")).toBeTruthy();
    expect(screen.getByText("Pídeselo a Amacrux.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Pedir saldo|Recargar|Comprar/ })).toBeNull();
    // Said once: the line under the balance does not repeat whom to ask.
    expect(screen.queryByText("Para recargar, habla con Amacrux.")).toBeNull();
  });

  it("«No llega a fin de mes» without enough days to estimate says so; «Agotada» says what happens", async () => {
    await view(summary({ bag_state: "not_enough", days_left: null }));
    expect(screen.getByText("No llega a fin de mes")).toBeTruthy();
    expect(screen.getByText("Aún no hay datos para estimarlo.")).toBeTruthy();
    await view(summary({ bag_state: "empty", days_left: 0 }));
    expect(screen.getByText("Agotada")).toBeTruthy();
    expect(screen.getByText("Sin saldo: las conversaciones pasan a la Bandeja hasta que se asigne más.")).toBeTruthy();
  });

  it("the balance in the bag's currency; all well, no notice", async () => {
    await view(summary({ bag_state: "ok" }));
    expect(screen.queryByTestId("usage-bag")).toBeNull();
    // The matcher folds the non-breaking space Intl puts before «€».
    const amount = formatMoney(120000, "es", "EUR").replace(/[.$]/g, "\\$&").replace(/\s/g, "\\s");
    expect(screen.getByLabelText(new RegExp(`^Saldo disponible: ${amount}`))).toBeTruthy();
    expect(formatMoney(1250, "es", "EUR")).toMatch(/12,50\s?€/);
    expect(formatMoney(1250, "es", "???")).toBe(formatMoney(1250, "es"));
  });
});
