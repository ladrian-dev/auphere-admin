import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import type { ThreadItem } from "@/api/endpoints";
import { eventText, withDaySeparators } from "@/features/inbox/model";
import { EventLine, MessageBubble } from "@/features/inbox/thread/bubble";
import { motionFor } from "@/motion/use-motion";
import { t as translate, type MessageKey } from "@/i18n/t";

/**
 * Spec 031 (T070, R5.3, R5.6, R14.7): the thread.
 */
const t = (k: MessageKey, v?: Record<string, string | number>) => translate("es", k, v);
jest.mock("@/features/inbox/thread/media", () => ({
  mediaUrl: (id: string) => `http://api/console/lite/inbox/messages/${id}/media`,
  mediaHeaders: async () => ({ Authorization: "Bearer tok", "X-App-Platform": "ios", "X-App-Version": "1.0.0" }),
}));
const mockImage = jest.fn();
jest.mock("expo-image", () => ({ Image: (p: unknown) => (mockImage(p), null) }));

const msg = (o: Partial<ThreadItem>): ThreadItem =>
  ({
    type: "message",
    id: "m1",
    at: "2026-10-08T10:15:00Z",
    direction: "inbound",
    author: { kind: "contact", name: "Ana", is_me: false },
    text: "Hola",
    media: null,
    delivery: null,
    failure_reason: null,
    kind: null,
    detail: null,
    ...o,
  }) as ThreadItem;

const view = (item: ThreadItem, onOpen = jest.fn()) => render(<MessageBubble item={item} t={t} locale="es" onOpen={onOpen} />);

it("the contact's message, unnamed, on its side", async () => {
  await view(msg({}));
  expect(screen.getByLabelText(/^El contacto\. Hola\./)).toBeTruthy();
});

it("the agent's and a person's messages say who", async () => {
  await view(msg({ direction: "outbound", author: { kind: "agent", name: null, is_me: false }, delivery: "delivered" }));
  expect(screen.getByText("Agente")).toBeTruthy();
  expect(screen.getByText("· Entregado")).toBeTruthy();
  await view(msg({ id: "m2", direction: "outbound", author: { kind: "member", name: "Luis", is_me: false }, delivery: "read" }));
  expect(screen.getByText("Luis")).toBeTruthy();
});

it("a failed send says why", async () => {
  await view(msg({ direction: "outbound", author: { kind: "member", name: null, is_me: true }, delivery: "failed", failure_reason: "número no válido" }));
  expect(screen.getByText("· No se envió: número no válido")).toBeTruthy();
});

it("a received image is fetched with the phone's credential", async () => {
  await view(msg({ id: "img1", text: null, media: { kind: "image", filename: null, transcript: null } }));
  await waitFor(() => expect(mockImage).toHaveBeenCalled());
  const props = mockImage.mock.calls.at(-1)![0] as { source: { uri: string; headers: Record<string, string> } };
  expect(props.source.uri).toContain("/messages/img1/media");
  expect(props.source.headers.Authorization).toBe("Bearer tok");
});

it("a document opens in the system's viewer", async () => {
  const onOpen = jest.fn();
  await view(msg({ id: "doc1", text: null, media: { kind: "document", filename: "factura.pdf", transcript: null } }), onOpen);
  await fireEvent.press(screen.getByRole("button", { name: "Abrir factura.pdf" }));
  expect(onOpen).toHaveBeenCalledWith("doc1", "application/pdf");
});

it("system notices read as sentences, with «Tú» verbs for this person", async () => {
  await render(<EventLine item={msg({ type: "event", kind: "escalated", detail: "Quiere hablar con alguien" })} t={t} />);
  expect(screen.getByText("El agente pidió ayuda: Quiere hablar con alguien")).toBeTruthy();
  expect(eventText("takeover", { kind: "member", name: null, is_me: true }, null, t)).toBe("Tomaste el control");
  expect(eventText("released", { kind: "member", name: "Luis", is_me: false }, null, t)).toBe("Luis se la devolvió al agente");
  expect(eventText("reopened", { kind: "contact", name: "Ana", is_me: false }, null, t)).toBe("El contacto volvió a escribir y se reabrió");
});

it("days are separated", () => {
  const rows = withDaySeparators([msg({ id: "a", at: "2026-10-07T10:00:00Z" }), msg({ id: "b", at: "2026-10-08T10:00:00Z" }), msg({ id: "c", at: "2026-10-08T11:00:00Z" })]);
  expect(rows.map((r) => r.kind)).toEqual(["day", "item", "day", "item", "item"]);
});

it("with reduced motion, entrances are fades only", () => {
  const m = motionFor(true);
  expect(m.enter).toBe(m.fade);
  expect(m.layout).toBeUndefined();
});
