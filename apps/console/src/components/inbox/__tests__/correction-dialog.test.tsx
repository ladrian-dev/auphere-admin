import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { InboxThreadItem } from "@/lib/backend/inbox";
import type { Correction } from "@/lib/backend/inbox-corrections";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/inbox/correction-actions", () => ({}));

const { CorrectionDialog } = await import("../correction-dialog");
const { piiSpans } = await import("@/components/lite/lite-agents-model");
const { Thread } = await import("../thread");
type Actions = NonNullable<React.ComponentProps<typeof CorrectionDialog>["actions"]>;

/**
 * Spec 047 (T176; requisitos 52.1 a 52.6) — «Corregir esta respuesta»: el
 * texto y el alcance (siempre elegido), el tipo a la vista antes de enviar, la
 * paráfrasis editable, los datos personales que bloquean el envío diciendo
 * cuáles, enviar y deshacer un dato.
 */

const CONV = "00000000-0000-4000-8000-000000000c01";
const MSG = "00000000-0000-4000-8000-000000000a01";
const ID = "00000000-0000-4000-8000-000000000f01";

const message: InboxThreadItem = {
  type: "message",
  id: MSG,
  at: "2026-10-27T10:00:00Z",
  direction: "outbound",
  author: { kind: "agent", name: "Recepción", is_me: false },
  text: "No tenemos aparcamiento, lo siento.",
  media: null,
  delivery: "read",
  failure_reason: null,
  kind: null,
  detail: null,
};

function correction(over: Partial<Correction> = {}): Correction {
  return {
    id: ID,
    revision: 1,
    status: "draft",
    kind: "data",
    scope: "business",
    lesson: "El aparcamiento está en la calle de atrás",
    paraphrase: "¿Dónde se puede aparcar?",
    pii: [],
    agent: { id: "a1", name: "Recepción" },
    applied_change_id: null,
    proposal_id: null,
    created_at: "2026-10-27T10:01:00Z",
    sent_at: null,
    undone_at: null,
    ...over,
  };
}

const ok = <T,>(data: T) => ({ ok: true as const, data });

function view(over: Partial<Actions> = {}) {
  const actions: Actions = {
    create: vi.fn(async () => ok(correction())),
    edit: vi.fn(async (b) => ok(correction({ revision: 2, lesson: b.lesson ?? "", paraphrase: b.paraphrase ?? null }))),
    send: vi.fn(async () => ok(correction({ status: "applied", revision: 3, sent_at: "2026-10-27T10:02:00Z", applied_change_id: "c1" }))),
    undo: vi.fn(async () => ok(correction({ status: "undone", revision: 4 }))),
    ...over,
  };
  const onClose = vi.fn();
  const r = render(
    <LocaleProvider locale="es">
      <CorrectionDialog conversationId={CONV} message={message} onClose={onClose} actions={actions} />
    </LocaleProvider>,
  );
  return { ...r, actions, onClose };
}

async function write(user: ReturnType<typeof userEvent.setup>, scope: "Todo el negocio" | "Solo este agente" | null) {
  const dialog = await screen.findByRole("dialog", { name: "Corregir esta respuesta" });
  await user.type(within(dialog).getByRole("textbox", { name: /Cómo debió responder/ }), "El aparcamiento está en la calle de atrás");
  if (scope) await user.click(within(dialog).getByRole("radio", { name: new RegExp(scope) }));
  await user.click(within(dialog).getByRole("button", { name: "Continuar" }));
  return dialog;
}

describe("«Corregir esta respuesta» (T176)", { timeout: 30_000 }, () => {
  it("pide el texto y el alcance, que no viene elegido; enseña la respuesta y pasa axe", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    const dialog = await screen.findByRole("dialog", { name: "Corregir esta respuesta" });
    expect(within(dialog).getByText("No tenemos aparcamiento, lo siento.")).toBeInTheDocument();
    for (const radio of within(dialog).getAllByRole("radio")) expect(radio).not.toBeChecked();
    expect(await axeViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Continuar" }));
    expect(within(dialog).getByText("Escribe cómo debió responder.")).toBeInTheDocument();
    expect(within(dialog).getByText("Elige para quién vale.")).toBeInTheDocument();
    expect(actions.create).not.toHaveBeenCalled();
  });

  it("un dato: se ve el tipo antes de enviar, se guarda y se puede deshacer", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    const dialog = await write(user, "Todo el negocio");
    await waitFor(() =>
      expect(actions.create).toHaveBeenCalledWith(expect.objectContaining({ conversation: CONV, message: MSG, scope: "business", text: "El aparcamiento está en la calle de atrás" })),
    );
    expect(vi.mocked(actions.create).mock.calls[0]![0].key).toMatch(/.{8,}/);
    expect(await within(dialog).findByText("Es un dato")).toBeInTheDocument();
    expect(within(dialog).getByText(/Se guarda al momento en la ficha de tu negocio/)).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: /Lo que preguntó el cliente/ })).toHaveValue("¿Dónde se puede aparcar?");
    expect(await axeViolations()).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Guardar el dato" }));
    await waitFor(() => expect(actions.send).toHaveBeenCalledWith({ id: ID, revision: 1 }));
    expect(actions.edit).not.toHaveBeenCalled();
    expect(await within(dialog).findByText("Hecho. Recepción lo sabe desde el siguiente mensaje.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Deshacer" }));
    await waitFor(() => expect(actions.undo).toHaveBeenCalledWith({ id: ID }));
    expect(await within(dialog).findByText("Deshecho. El agente vuelve a responder como antes.")).toBeInTheDocument();
  });

  it("datos personales: dice cuáles y dónde, y no deja enviar hasta quitarlos; lo editado se revisa antes de enviar", async () => {
    const user = userEvent.setup();
    const phone = "+34 600 11 22 33";
    const paraphrase = `¿Me llamáis al ${phone}?`;
    const start = paraphrase.indexOf(phone);
    const { actions } = view({
      create: vi.fn(async () => ok(correction({ kind: "behavior", lesson: "No des citas los festivos", paraphrase, pii: [{ field: "paraphrase", kind: "phone", start, end: start + phone.length }] }))),
      edit: vi.fn(async (b) => ok(correction({ kind: "behavior", revision: 2, lesson: b.lesson ?? "", paraphrase: b.paraphrase ?? null, pii: [] }))),
      send: vi.fn(async () => ok(correction({ kind: "behavior", status: "proposed", revision: 3 }))),
    });
    const dialog = await write(user, "Solo este agente");
    expect(await within(dialog).findByText("Es un comportamiento")).toBeInTheDocument();
    const pii = within(dialog).getByRole("alert");
    expect(within(pii).getByText(`Un teléfono en lo que preguntó el cliente: «${phone}»`)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Enviar la propuesta" })).toBeDisabled();

    const field = within(dialog).getByRole("textbox", { name: /Lo que preguntó el cliente/ });
    await user.clear(field);
    await user.type(field, "¿Me podéis llamar?");
    expect(within(dialog).getByText("Lo volvemos a comprobar al enviar.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Enviar la propuesta" }));
    await waitFor(() => expect(actions.edit).toHaveBeenCalledWith({ id: ID, revision: 1, lesson: "No des citas los festivos", paraphrase: "¿Me podéis llamar?" }));
    await waitFor(() => expect(actions.send).toHaveBeenCalledWith({ id: ID, revision: 2 }));
    expect(await within(dialog).findByText(/Quien gestiona tus agentes lo verá en las mejoras del agente/)).toBeInTheDocument();
  });

  it("un «no» del envío llega en palabras: falta la paráfrasis, la regla es larga, ya no es de un agente", async () => {
    const user = userEvent.setup();
    const send = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 422, message: "x", code: "paraphrase_required", info: {} })
      .mockResolvedValueOnce({ ok: false, status: 422, message: "x", code: "rule_too_long", info: { max: 300 } });
    view({ send });
    const dialog = await write(user, "Todo el negocio");
    await user.click(await within(dialog).findByRole("button", { name: "Guardar el dato" }));
    // Una vez, bajo su campo (recorrido UI: salía también abajo, repetido).
    expect(await within(dialog).findAllByText("Escribe lo que preguntó el cliente. Es la pregunta que verá el agente.")).toHaveLength(1);
    await user.click(within(dialog).getByRole("button", { name: "Guardar el dato" }));
    expect(await within(dialog).findByText("La regla es demasiado larga. Como mucho 300 caracteres.")).toBeInTheDocument();
  });

  it("si la respuesta no es del agente, lo dice sin crear nada", async () => {
    const user = userEvent.setup();
    view({ create: vi.fn(async () => ({ ok: false as const, status: 422, message: "x", code: "not_an_agent_reply" })) });
    const dialog = await write(user, "Todo el negocio");
    expect(await within(dialog).findByText("Solo se corrigen las respuestas del agente.")).toBeInTheDocument();
  });
});

describe("el hilo (52.1)", () => {
  it("ofrece «Corregir esta respuesta» solo sobre las respuestas del agente", async () => {
    const user = userEvent.setup();
    const onCorrect = vi.fn();
    const contact: InboxThreadItem = { ...message, id: "00000000-0000-4000-8000-000000000a02", direction: "inbound", author: { kind: "contact", name: "Ana", is_me: false }, text: "¿Tenéis aparcamiento?" };
    const member: InboxThreadItem = { ...message, id: "00000000-0000-4000-8000-000000000a03", author: { kind: "member", name: "Marta", is_me: true }, text: "Te llamo ahora" };
    render(
      <LocaleProvider locale="es">
        <Thread items={[contact, message, member]} hasOlder={false} loadingOlder={false} contactInitials="A" now={new Date("2026-10-27T12:00:00Z")} onOlder={() => {}} onCorrect={onCorrect} />
      </LocaleProvider>,
    );
    const buttons = screen.getAllByRole("button", { name: "Corregir esta respuesta" });
    expect(buttons).toHaveLength(1);
    await user.click(buttons[0]!);
    expect(onCorrect).toHaveBeenCalledWith(message);
  });
});

describe("piiSpans", () => {
  it("devuelve el trozo marcado y se salta una posición que ya no cae en el texto", () => {
    const texts = { lesson: "Llama a Ana", paraphrase: "ana@x.es" };
    expect(
      piiSpans(
        [
          { field: "lesson", kind: "name", start: 8, end: 11 },
          { field: "paraphrase", kind: "email", start: 0, end: 8 },
          { field: "paraphrase", kind: "phone", start: 5, end: 40 },
        ],
        texts,
      ),
    ).toEqual([
      { field: "lesson", kind: "name", text: "Ana" },
      { field: "paraphrase", kind: "email", text: "ana@x.es" },
    ]);
  });
});
