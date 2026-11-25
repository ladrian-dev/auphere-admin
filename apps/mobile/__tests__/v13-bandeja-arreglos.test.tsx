import { render, screen } from "@testing-library/react-native";

import type { ThreadItem } from "@/api/endpoints";
import { composerMode, eventText, modeLine } from "@/features/inbox/model";
import { EventLine } from "@/features/inbox/thread/bubble";
import { ControlCard } from "@/features/inbox/thread/control";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 069, Fase 3 (T020, T024): the visible bugs of the Bandeja, each one red
 * first. Requisitos 11.5, 11.7, 12.1 and 21.2.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);

jest.mock("@/features/inbox/thread/media", () => ({
  mediaUrl: (id: string) => `http://api/console/lite/inbox/messages/${id}/media`,
  mediaHeaders: async () => null,
}));

const noop = () => undefined;

describe("the agent's window expired (R11.5): never «responde el agente»", () => {
  const base = { assignee: null, waiting_reason: null, channel: { kind: "instagram", connected: true } } as const;

  it("Instagram past 24 h: the agent cannot answer, a person can until the window closes", () => {
    expect(composerMode({ ...base, state: "agent", window: { open: true, agent_open: false, closes_at: "2026-11-27T10:00:00Z" } })).toMatchObject({
      kind: "agent",
      personUntil: "2026-11-27T10:00:00Z",
    });
  });

  it("the window closed for everybody: it says the agent can answer when they write again", () => {
    expect(composerMode({ ...base, state: "agent", window: { open: false, agent_open: false, closes_at: null } })).toMatchObject({ kind: "agent", windowClosed: true });
  });

  it("with the agent's window open, nothing changes", () => {
    expect(composerMode({ ...base, state: "agent", window: { open: true, agent_open: true, closes_at: "2026-11-27T10:00:00Z" } })).toEqual({ kind: "agent", agent: null });
  });

  it("the strip says until when a person can answer, and not that the agent answers", async () => {
    await render(
      <ControlCard
        mode={{ kind: "agent", agent: "Recepción", personUntil: "2026-11-27T10:00:00Z" }}
        busy={false}
        online
        t={t}
        onTakeOver={noop}
        onGiveBack={noop}
        onReopen={noop}
      />,
    );
    expect(screen.queryByText(/^Responde /)).toBeNull();
    expect(screen.getByText(/Tú sí puedes hasta el/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tomar el control" })).toBeTruthy();
  });

  it("closed for everybody: the console's sentence, with the agent's name as the header says it (review H23)", async () => {
    await render(<ControlCard mode={{ kind: "agent", agent: "Recepción", windowClosed: true }} busy={false} online t={t} onTakeOver={noop} onGiveBack={noop} onReopen={noop} />);
    expect(screen.queryByText(/^Responde /)).toBeNull();
    expect(screen.getByText("Recepción ya no puede responder: pasó el plazo desde el último mensaje del contacto. Podrá hacerlo cuando vuelva a escribir.")).toBeTruthy();
  });

  it("without the agent's name, the console's own sentence", async () => {
    await render(<ControlCard mode={{ kind: "agent", agent: null, windowClosed: true }} busy={false} online t={t} onTakeOver={noop} onGiveBack={noop} onReopen={noop} />);
    expect(screen.getByText(t("inbox.composer.agent_window_closed"))).toBeTruthy();
  });

  it("past the agent's 24 h, with its name too", async () => {
    await render(<ControlCard mode={{ kind: "agent", agent: "Recepción", personUntil: "2026-11-27T10:00:00Z" }} busy={false} online t={t} onTakeOver={noop} onGiveBack={noop} onReopen={noop} />);
    expect(screen.getByText(/^Recepción ya no puede responder: pasaron 24 horas/)).toBeTruthy();
  });
});

describe("the header's line with the agent's window expired (R11.5)", () => {
  const ava = { state: "agent", assignee: null, agent: { name: "Ava" } } as const;

  it("closed for everybody: not «Atiende Ava»", () => {
    expect(modeLine({ ...ava, window: { open: false, agent_open: false, closes_at: null } }, t)).toEqual({ kind: "paused", text: "Ava ya no puede responder" });
  });

  it("Instagram past the agent's 24 h: not «Atiende Ava» either", () => {
    expect(modeLine({ ...ava, window: { open: true, agent_open: false, closes_at: "2026-11-27T10:00:00Z" } }, t)).toEqual({ kind: "paused", text: "Ava ya no puede responder" });
  });

  it("without a name, the agent", () => {
    expect(modeLine({ ...ava, agent: null, window: { open: false, agent_open: false, closes_at: null } }, t).text).toBe("El agente ya no puede responder");
  });

  it("with the window open, or without knowing it (the list), it still says who answers", () => {
    expect(modeLine({ ...ava, window: { open: true, agent_open: true, closes_at: null } }, t)).toEqual({ kind: "agent", text: "Atiende Ava" });
    expect(modeLine(ava, t)).toEqual({ kind: "agent", text: "Atiende Ava" });
  });
});

describe("closed for inactivity (R11.7, spec 064 R5.2)", () => {
  const system = { kind: "system" as const, name: null, is_me: false };

  it("the event says it with those words, not who", () => {
    expect(eventText("resolved", system, "inactivity", t)).toBe("Se cerró por inactividad");
    // A person resolving it still reads as before.
    expect(eventText("resolved", { kind: "member", name: null, is_me: true }, null, t)).toBe("La marcaste como resuelta");
  });

  it("the thread line too", async () => {
    const item = { type: "event", id: "e1", at: "2026-11-20T10:00:00Z", kind: "resolved", author: system, detail: "inactivity" } as ThreadItem;
    await render(<EventLine item={item} t={t} />);
    expect(screen.getByText("Se cerró por inactividad")).toBeTruthy();
  });
});
