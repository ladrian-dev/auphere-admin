import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { Composer } from "../composer";
import { ContactPanel } from "../contact-panel";
import { ConversationRow } from "../conversation-row";
import { composerMode } from "../inbox-model";
import { Thread } from "../thread";
import { NOW, conversation, detail, message } from "./fixtures";

const since = new Date(NOW.getTime() - 5 * 60_000).toISOString();
const AGENT = { kind: "agent" as const, name: null, is_me: false };
const SYSTEM = { kind: "system" as const, name: null, is_me: false };

function inSpanish(node: React.ReactNode) {
  return render(<LocaleProvider locale="es">{node}</LocaleProvider>);
}

function row(code: string | null, reason: string | null) {
  inSpanish(
    <ConversationRow
      conversation={conversation({ state: "waiting", waiting: { reason, since }, waiting_reason: code })}
      selected={false}
      onOpen={vi.fn()}
      now={NOW}
    />,
  );
}

function composer(code: string | null, reason: string | null) {
  const mode = composerMode(detail({ state: "waiting", waiting_code: code, waiting_reason: reason }));
  inSpanish(
    <Composer
      mode={mode}
      busy={false}
      sendError={null}
      replies={[]}
      repliesApi={{ create: vi.fn(async () => true), edit: vi.fn(async () => true), archive: vi.fn(async () => true) }}
      attaching={null}
      onTakeOver={vi.fn()}
      onGiveBack={vi.fn()}
      onReopen={vi.fn()}
      onSend={vi.fn(async () => true)}
      onAttach={vi.fn()}
    />,
  );
}

function thread(detailText: string, author: typeof AGENT | typeof SYSTEM = SYSTEM) {
  inSpanish(
    <Thread
      items={[message({ id: "e", type: "event", kind: "escalated", author, detail: detailText, text: null })]}
      hasOlder={false}
      loadingOlder={false}
      contactInitials="AT"
      now={NOW}
      onOlder={vi.fn()}
    />,
  );
}

function activity(detailText: string) {
  inSpanish(
    <ContactPanel
      detail={detail({ activity: [{ kind: "escalated", at: since, actor: SYSTEM, detail: detailText }] })}
      initials="AT"
      suggested={[]}
      now={NOW}
      onClose={vi.fn()}
      onTags={vi.fn(async () => true)}
      onNote={vi.fn(async () => true)}
    />,
  );
}

/**
 * Spec 056 (requisito 7): every reason the Inbox paints —the row, the thread,
 * the composer and the activity— goes through the builder's table. A code it
 * does not know reads «El agente pidió ayuda», never the code; the agent's own
 * words go as they are.
 */
describe("the reason a conversation waits, in words", () => {
  it("the row reads the column's code first", () => {
    row("agent_unpublished", "agent_unpublished");
    expect(screen.getByText("Agente sin publicar")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("agent_unpublished");
  });

  it("the row: an unknown code is the generic sentence, the agent's words go as they are", () => {
    row("brand_new_reason", "brand_new_reason");
    expect(screen.getByText("El agente pidió ayuda")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("brand_new_reason");
  });

  it("the row: an escalation keeps what the agent wrote", () => {
    row("escalated", "Pide un reembolso");
    expect(screen.getByText("Pide un reembolso")).toBeInTheDocument();
  });

  it("the composer", () => {
    composer("agent_unpublished", "agent_unpublished");
    expect(screen.getByText("Agente sin publicar")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("agent_unpublished");
  });

  it("the composer: an unknown code is the generic sentence", () => {
    composer("nuevo_motivo", null);
    expect(screen.getByText("El agente pidió ayuda")).toBeInTheDocument();
  });

  it("the composer: the booking brake says what happened", () => {
    composer("booking_unbacked", "booking_unbacked");
    expect(screen.getByText("El agente dio por hecha una cita que no existe")).toBeInTheDocument();
  });

  it("the composer: an appointment while the agenda is not ready (spec 057, 4.2)", () => {
    composer("agenda_not_ready", "agenda_not_ready");
    expect(screen.getByText("Pidió una cita y la agenda aún no está lista")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("agenda_not_ready");
  });

  it("the thread", () => {
    thread("agent_unpublished");
    expect(screen.getByRole("note")).toHaveTextContent("Agente sin publicar");
    expect(screen.getByRole("note")).not.toHaveTextContent("agent_unpublished");
  });

  it("the thread: an unknown code and the agent's own words", () => {
    thread("otro_codigo");
    expect(screen.getByRole("note")).toHaveTextContent(/^El agente pidió ayuda ·/);
  });

  it("the thread: the agent's words, with the sentence", () => {
    thread("Pide un reembolso", AGENT);
    expect(screen.getByRole("note")).toHaveTextContent("El agente pidió ayuda: Pide un reembolso");
  });

  it("the activity", () => {
    activity("agent_unpublished");
    expect(screen.getByText(/Agente sin publicar/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("agent_unpublished");
  });

  it("the activity: an unknown code", () => {
    activity("codigo_nuevo");
    expect(screen.getByText(/^El agente pidió ayuda/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("codigo_nuevo");
  });
});
