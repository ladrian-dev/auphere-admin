import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import type { ThreadItem } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import { keys } from "@/api/query";
import { correctionErrorText, piiItems } from "@/features/inbox/correction";
import { MessageBubble } from "@/features/inbox/thread/bubble";
import { t as translate, type T } from "@/i18n/t";
import { clearDrafts, peekDraft } from "@/lib/drafts";

import { CONVERSATION, correction, MESSAGE, Providers, testClient } from "../test/fabrica-fixtures";

/**
 * Spec 047, T176 (requirement 52): «Corregir esta respuesta» in the app's
 * conversation — the text and the scope; whether it is a fact or a behaviour,
 * before sending; the paraphrase, editable; personal data blocks sending; a
 * fact can be undone.
 */
const t: T = (k, v) => translate("es", k, v);
// Whole screens with a real query cache: a loaded machine running the suite in parallel needs more than 5 s.
jest.setTimeout(15_000);

const mockEndpoints = {
  me: jest.fn(),
  conversation: jest.fn(),
  thread: jest.fn(),
  business: jest.fn(),
  draftCorrection: jest.fn(),
  editCorrection: jest.fn(),
  sendCorrection: jest.fn(),
  undoCorrection: jest.fn(),
};
jest.mock("@/api/endpoints", () => ({ endpoints: new Proxy({}, { get: (_t, k: string) => (mockEndpoints as Record<string, unknown>)[k] }) }));
jest.mock("@/api/reservas", () => ({ demo: null }));
let mockOnline = true;
jest.mock("@/ui/online", () => ({ useOnline: () => mockOnline }));
const mockBack = jest.fn();
jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ id: "44444444-4444-4444-8444-444444444444", message: "55555555-5555-4555-8555-555555555555" }),
  router: { back: (...a: unknown[]) => mockBack(...a), push: jest.fn() },
}));

const me = { user: { name: "Valeria", email: "v@flor.test" }, client: { name: "Flor y Encanto", modules: ["inbox"] }, nav: ["inbox"], agents: [], channels: [], balance_contact: { kind: "partner", name: "Amacrux" }, business: { timezone: "America/Santiago", hours: null, hours_label: null } };
const answer: ThreadItem = { id: MESSAGE, type: "message", direction: "outbound", at: "2026-10-28T11:00:00Z", text: "No tenemos aparcamiento, lo siento.", author: { kind: "agent", name: "Recepción", is_me: false } } as ThreadItem;

// Loaded once, outside any test's time.
const Route = require("@/app/conversacion/[id]/corregir").default as () => React.JSX.Element;

async function open() {
  const client = testClient();
  client.setQueryData(keys.me, me);
  client.setQueryData(keys.conversation(CONVERSATION), { id: CONVERSATION, handled_by_agent: { id: "a", name: "Recepción" }, agent: null });
  client.setQueryData(keys.thread(CONVERSATION), { pages: [{ items: [answer], next_before: null }], pageParams: [null] });
  await render(
    <Providers client={client}>
      <Route />
    </Providers>,
  );
}

beforeEach(() => {
  clearDrafts();
  mockOnline = true;
  mockBack.mockReset();
  for (const f of Object.values(mockEndpoints)) f.mockReset();
  mockEndpoints.me.mockResolvedValue(me);
  mockEndpoints.conversation.mockResolvedValue({ id: CONVERSATION, handled_by_agent: { id: "a", name: "Recepción" }, agent: null });
  mockEndpoints.thread.mockResolvedValue({ items: [answer], next_before: null });
  mockEndpoints.business.mockResolvedValue({});
});

describe("under each answer of the agent (52.1)", () => {
  const bubble = (item: ThreadItem, onCorrect = jest.fn()) => render(<MessageBubble item={item} t={t} locale="es" onOpen={jest.fn()} onCorrect={onCorrect} />);

  it("the agent's answers have «Corregir esta respuesta»; the contact's and a person's do not", async () => {
    const onCorrect = jest.fn();
    await bubble(answer, onCorrect);
    await fireEvent.press(screen.getByRole("button", { name: "Corregir esta respuesta" }));
    expect(onCorrect).toHaveBeenCalledWith(MESSAGE);
    await bubble({ ...answer, direction: "inbound", author: { kind: "contact", name: "Ana", is_me: false } } as ThreadItem);
    expect(screen.queryByRole("button", { name: "Corregir esta respuesta" })).toBeNull();
    await bubble({ ...answer, author: { kind: "member", name: "Luis", is_me: false } } as ThreadItem);
    expect(screen.queryByRole("button", { name: "Corregir esta respuesta" })).toBeNull();
  });
});

describe("the pure parts", () => {
  it("personal data is said with its words while the field is as the API saw it", () => {
    const c = correction({ paraphrase: "Ana López preguntó dónde aparcar.", pii: [{ field: "paraphrase", kind: "name", start: 0, end: 9 }] });
    expect(piiItems(c, { lesson: false, paraphrase: false })).toEqual([{ field: "paraphrase", kind: "name", text: "Ana López" }]);
    // Edited: the offsets no longer match — what and where, not the words.
    expect(piiItems(c, { lesson: false, paraphrase: true })).toEqual([{ field: "paraphrase", kind: "name", text: "" }]);
  });

  it("refusals in words", () => {
    expect(correctionErrorText(new ApiError(422, "not_an_agent_reply"), t)).toBe("Solo se pueden corregir las respuestas del agente.");
    expect(correctionErrorText(new ApiError(422, "lesson_too_long", { max: 2000 }), t)).toBe("Como mucho 2000 caracteres.");
    expect(correctionErrorText(new ApiError(0, "offline"), t)).toMatch(/^Sin conexión: no se envía nada/);
  });
});

describe("«Corregir esta respuesta» (T176)", () => {
  /** Up to the review of a fact: the text and the scope sent, and what it is said before sending. */
  async function reviewFact() {
    mockEndpoints.draftCorrection.mockResolvedValue(correction());
    await open();
    await fireEvent.changeText(screen.getByLabelText("¿Cómo debió responder?"), "El aparcamiento está en la calle de atrás.");
    await fireEvent.press(screen.getByRole("radio", { name: "Solo este agente" }));
    await fireEvent.press(screen.getByRole("button", { name: "Continuar" }));
    await screen.findByText("Es un dato");
  }

  it("quotes the answer being corrected, and «Continuar» waits for a text (52.1)", async () => {
    await open();
    expect(screen.getByText("No tenemos aparcamiento, lo siento.")).toBeTruthy();
    expect(screen.getByText("Lo que respondió Recepción")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continuar" }).props.accessibilityState).toMatchObject({ disabled: true });
  });

  it("a fact: text and scope, then what it is before sending, with the paraphrase to edit (52.2, 52.4)", async () => {
    await reviewFact();
    expect(mockEndpoints.draftCorrection).toHaveBeenCalledWith(CONVERSATION, MESSAGE, { text: "El aparcamiento está en la calle de atrás.", scope: "agent" }, expect.any(String));
    expect(screen.getByLabelText("Lo que preguntó el cliente").props.value).toBe("Preguntó dónde aparcar.");
    expect(screen.getByText(/es lo que verá Amacrux\. El mensaje del cliente no sale de aquí\./)).toBeTruthy();
  });

  it("a fact sent applies at once and can be undone (52.2)", async () => {
    await reviewFact();
    mockEndpoints.sendCorrection.mockResolvedValue(correction({ status: "applied", sent_at: "2026-10-28T12:01:00Z" }));
    await fireEvent.press(screen.getByRole("button", { name: "Enviar la corrección" }));
    expect(mockEndpoints.editCorrection).not.toHaveBeenCalled();
    expect(mockEndpoints.sendCorrection).toHaveBeenCalledWith(correction().id, 1, expect.any(String));
    expect(await screen.findByText("Corregido. Recepción lo usa desde el siguiente mensaje.")).toBeTruthy();
    expect(peekDraft(`corregir.${MESSAGE}`)).toBeUndefined();

    mockEndpoints.undoCorrection.mockResolvedValue(correction({ status: "undone" }));
    await fireEvent.press(screen.getByRole("button", { name: "Deshacer" }));
    expect(await screen.findByText("Deshecho. Recepción vuelve a lo de antes.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Listo" }));
    expect(mockBack).toHaveBeenCalled();
  });

  it("a behaviour reaches the partner as a proposal: said before, and no undo after (52.2)", async () => {
    mockEndpoints.draftCorrection.mockResolvedValue(correction({ kind: "behavior", lesson: "No des citas los festivos." }));
    mockEndpoints.sendCorrection.mockResolvedValue(correction({ kind: "behavior", status: "proposed" }));
    await open();
    await fireEvent.changeText(screen.getByLabelText("¿Cómo debió responder?"), "No des citas los festivos.");
    await fireEvent.press(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByText("Es un comportamiento")).toBeTruthy();
    expect(screen.getByText("Le llega a Amacrux como propuesta, con una prueba para que no vuelva a pasar. Decide Amacrux.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Enviar la corrección" }));
    expect(await screen.findByText("Enviado a Amacrux. Lo revisará y decidirá si Recepción lo aprende.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Deshacer" })).toBeNull();
  });

  it("personal data blocks sending until it is removed; the edit is checked again first (52.5)", async () => {
    const withName = correction({ paraphrase: "Ana López preguntó dónde aparcar.", pii: [{ field: "paraphrase", kind: "name", start: 0, end: 9 }] });
    mockEndpoints.draftCorrection.mockResolvedValue(withName);
    await open();
    await fireEvent.changeText(screen.getByLabelText("¿Cómo debió responder?"), "Está en la calle de atrás.");
    await fireEvent.press(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByText("Quita los datos personales antes de enviar")).toBeTruthy();
    expect(screen.getByText("• Un nombre en «Lo que preguntó el cliente»: Ana López")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Enviar la corrección" }).props.accessibilityState).toMatchObject({ disabled: true });

    await fireEvent.changeText(screen.getByLabelText("Lo que preguntó el cliente"), "Preguntó dónde aparcar.");
    const clean = correction({ revision: 2 });
    mockEndpoints.editCorrection.mockResolvedValue(clean);
    mockEndpoints.sendCorrection.mockResolvedValue({ ...clean, status: "applied" });
    await fireEvent.press(screen.getByRole("button", { name: "Enviar la corrección" }));
    expect(mockEndpoints.editCorrection).toHaveBeenCalledWith(withName.id, { paraphrase: "Preguntó dónde aparcar." }, 1);
    expect(mockEndpoints.sendCorrection).toHaveBeenCalledWith(withName.id, 2, expect.any(String));
  });

  it("a 422 `pii_present` on sending shows what to remove, and nothing is saved", async () => {
    mockEndpoints.draftCorrection.mockResolvedValue(correction());
    mockEndpoints.sendCorrection.mockRejectedValue(new ApiError(422, "pii_present", { pii: [{ field: "lesson", kind: "phone", start: 0, end: 2 }] }));
    await open();
    await fireEvent.changeText(screen.getByLabelText("¿Cómo debió responder?"), "Llamar al 600 111 222");
    await fireEvent.press(screen.getByRole("button", { name: "Continuar" }));
    await fireEvent.press(await screen.findByRole("button", { name: "Enviar la corrección" }));
    expect(await screen.findByText(/^• Un teléfono en «Lo que aprende el agente»/)).toBeTruthy();
  });

  it("offline: nothing is sent, and what was typed is kept (50.5)", async () => {
    mockOnline = false;
    await open();
    await fireEvent.changeText(screen.getByLabelText("¿Cómo debió responder?"), "El parking está detrás.");
    expect(screen.getByText("Sin conexión: no se envía nada. Lo que escribiste sigue aquí hasta que vuelva la conexión.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continuar" }).props.accessibilityState).toMatchObject({ disabled: true });
    expect(mockEndpoints.draftCorrection).not.toHaveBeenCalled();
    await waitFor(() => expect(peekDraft(`corregir.${MESSAGE}`)).toEqual({ text: "El parking está detrás.", scope: "business" }));
  });
});
