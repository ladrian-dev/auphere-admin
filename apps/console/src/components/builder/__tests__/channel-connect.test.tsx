import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import { t as translate } from "@/i18n/messages";
import type { AgentChannels } from "@/lib/backend/channel-config-types";
import type { WhatsAppSignupResult } from "@/lib/backend/channels";

import { CH, HISTORY, LINK, RECEPCION, REF, channels, fail, ok, page } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
const sdk = vi.hoisted(() => ({ loginWithMeta: vi.fn(), whatsappSignupAction: vi.fn(), loginForCode: vi.fn(), metaSocialConnectAction: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => router }));
vi.mock("@/app/(console)/clients/[ref]/agents/channel-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  whatsappSignupAction: sdk.whatsappSignupAction,
  listCatalogsAction: vi.fn(),
  metaSocialConnectAction: sdk.metaSocialConnectAction,
  metaSocialCompleteAction: vi.fn(),
}));
vi.mock("@/lib/meta-fb-sdk", () => ({ loginWithMeta: sdk.loginWithMeta, loginForCode: sdk.loginForCode, SignupError: class extends Error {} }));

const { AgentChannelsPanel } = await import("../agent-channels");
const { ChannelConfigPage } = await import("../channel-page");
const { runWhatsAppSignup } = await import("@/components/channels/whatsapp-connect");
type Actions = NonNullable<React.ComponentProps<typeof AgentChannelsPanel>["actions"]>;

/**
 * Spec 047 (`evidence/prototipo/agente.md` §7, §10.1, §10.2 y hueco H4) — la
 * pestaña Canales del agente como el prototipo aprobado: sin canales, el
 * asistente de cuatro pasos y la rejilla (WhatsApp conectable, el resto
 * «Próximamente» o «Pendiente»); «Conectar WhatsApp» con Coexistencia
 * (recomendado) o Cloud API, que abre el alta de Meta que ya tiene la consola
 * con ese modo; «Compartir un enlace» con el enlace del dueño; con canales, la
 * lista con el logo de WhatsApp y «Añadir otro canal». El logo de WhatsApp
 * también en la cabecera de la página del canal.
 */

const META = { appId: "123", graphVersion: "v22.0", configIdCloudApi: "cfg-cloud", configIdCoexistence: "cfg-coex" };
const CH3 = "44444444-4444-4444-8444-444444444443";
const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate("es", key, vars);

const SIGNED: WhatsAppSignupResult = {
  status: "connected",
  channel_id: CH3,
  display_phone_number: "+34 600 11 22 33",
  mode: "cloud_api",
  used_channels: 1,
  max_channels: 3,
} as WhatsAppSignupResult;

const empty = (over: Partial<AgentChannels> = {}): AgentChannels => ({ channels: [], pending_link: null, ...over });
const fresh = page({
  id: CH3,
  identifier: "+34 600 11 22 33",
  visible_state: { code: "unconfigured", tone: "muted", reason: null },
  config: { ...page().config, audience: { mode: "unset", test_numbers: [], exceptions: [] }, escalation: { recipients: [], summary: true } },
});

function panel(data: AgentChannels = empty(), over: Partial<Actions> = {}, { canWrite = true, pages = {} as React.ComponentProps<typeof AgentChannelsPanel>["pages"] } = {}) {
  const actions: Actions = {
    reload: vi.fn(async () => ok(empty())),
    menu: { move: vi.fn(), pause: vi.fn(), resume: vi.fn(), disconnect: vi.fn() },
    ownerLink: {
      create: vi.fn(async ({ mode }) => ok({ id: LINK, url: "https://consola.auphere.com/connect/whatsapp/tok_abc", mode, expires_at: "2026-11-03T10:00:00Z" })),
      revoke: vi.fn(async () => ok(null)),
    },
    connect: {
      signup: vi.fn(async () => ({ ok: true as const, data: SIGNED })),
      move: vi.fn(async () => ok(fresh)),
      catalogs: vi.fn(async () => fail(409, "not_connected")),
    },
    ...over,
  };
  const view = render(
    <LocaleProvider locale="es">
      <AgentChannelsPanel refId={REF} agentId={RECEPCION} channels={data} pages={pages} canWrite={canWrite} clientName="Barbería Cultor" meta={META} actions={actions} />
    </LocaleProvider>,
  );
  return { ...view, actions };
}

const steps = () => within(screen.getByRole("list", { name: "Pasos", hidden: true })).getAllByRole("listitem", { hidden: true });
const grid = () => screen.getByRole("list", { name: "Canales" });

beforeEach(() => {
  toast.success.mockClear();
  toast.warning.mockClear();
  toast.error.mockClear();
  router.push.mockClear();
});

describe("sin canales: el asistente (§7.1)", () => {
  it("cuatro pasos, el primero en curso, y la rejilla de canales con Meta primero", async () => {
    const { container } = panel();
    expect(steps().map((li) => li.querySelector("[data-slot=step-title]")?.textContent)).toEqual(["Elegir canal", "Conectar", "Configurar el canal", "¡Listo!"]);
    expect(steps()[0]).toHaveAttribute("aria-current", "step");
    expect(within(steps()[0]!).getByText("Por dónde escribirán los clientes de este negocio.")).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "Elige un canal" })).toBeVisible();
    expect(screen.getByText(/Los de Meta van primero\. Un agente puede tener varios números del mismo canal\./)).toBeVisible();

    const cards = within(grid()).getAllByRole("listitem");
    expect(cards.map((c) => c.querySelector("[data-slot=channel-name]")?.textContent)).toEqual(["WhatsApp", "Messenger", "Instagram", "Threads", "TikTok", "Telegram", "X"]);
    expect(cards.map((c) => c.querySelector("[data-slot=brand-logo]")?.getAttribute("data-brand"))).toEqual(["whatsapp", "messenger", "instagram", "threads", "tiktok", "telegram", "x"]);
    expect(cards.map((c) => within(c).queryByText("Meta") !== null)).toEqual([true, true, true, true, false, false, false]);

    // Solo WhatsApp se conecta: es el único botón, con «Conectar →».
    const whatsapp = within(grid()).getByRole("button", { name: "Conectar WhatsApp" });
    expect(within(grid()).getAllByRole("button")).toHaveLength(1);
    expect(within(whatsapp).getByText("Atiende a los clientes en su número de WhatsApp Business, por la API de Meta.")).toBeVisible();
    expect(within(whatsapp).getByText("Coexistencia o Cloud API. El negocio puede seguir usando su app.")).toBeVisible();
    expect(within(whatsapp).getByText("Conectar")).toBeVisible();

    // El resto no es un botón: apagado, con su insignia y sin «Conectar».
    for (const [i, badge] of [[1, "Próximamente"], [2, "Próximamente"], [3, "Próximamente"], [4, "Pendiente"], [5, "Próximamente"], [6, "Próximamente"]] as const) {
      const card = cards[i]!.firstElementChild as HTMLElement;
      expect(card).toHaveAttribute("aria-disabled", "true");
      expect(within(card).getByText(badge)).toBeVisible();
      expect(within(card).queryByText(/Conectar/)).toBeNull();
    }
    expect(within(cards[4]!).getByText("Pendiente de la aprobación de TikTok.")).toBeVisible();
    // El prototipo lleva una nota interna en Instagram que no se copia.
    expect(grid().textContent).not.toMatch(/ADR|spec/i);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("quien solo lee no ve el asistente: el agente aún no tiene números", () => {
    panel(empty(), {}, { canWrite: false });
    expect(screen.queryByRole("heading", { name: "Elige un canal" })).toBeNull();
    expect(screen.getByText("Este agente aún no tiene ningún número.")).toBeVisible();
  });
});

describe("Conectar WhatsApp (§10.1)", () => {
  it("WhatsApp abre el modal: Coexistencia recomendada, Cloud API y compartir un enlace, en el paso 2", async () => {
    const user = userEvent.setup();
    const { baseElement } = panel();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));
    const dialog = await screen.findByRole("dialog", { name: "Conectar WhatsApp" });
    expect(within(dialog).getByText("Elige cómo se conecta el número de Barbería Cultor. Al continuar se abre la ventana de Meta.")).toBeVisible();
    const modes = within(dialog).getByRole("group", { name: "Modo de conexión" });
    expect(within(modes).getByRole("radio", { name: /^Coexistencia/ })).toBeChecked();
    expect(within(modes).getByText("Recomendado")).toBeVisible();
    expect(within(modes).getByText(/Mantener la app WhatsApp Business\. El equipo sigue respondiendo desde el móvil/)).toBeVisible();
    expect(within(modes).getByRole("radio", { name: /^Cloud API/ })).not.toBeChecked();
    expect(within(modes).getByText(/Número nuevo o migrado\. Si el número está en la app WhatsApp Business, deja de funcionar allí\./)).toBeVisible();
    expect(within(dialog).getByText("¿No tienes la cuenta de Meta del negocio?")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Compartir un enlace" })).toBeVisible();
    expect(within(dialog).getByText("Se abre una ventana nueva")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Cancelar" })).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Conectar" })).toBeEnabled();
    expect(steps()[1]).toHaveAttribute("aria-current", "step");
    expect(steps()[0]!.querySelector("[data-slot=step-done]")).not.toBeNull();
    expect(await axeViolations(baseElement)).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(steps()[0]).toHaveAttribute("aria-current", "step");
  });

  it("«Conectar» abre Meta con el modo elegido, el velo espera y el número queda en este agente", async () => {
    const user = userEvent.setup();
    let finish: (v: { ok: true; data: WhatsAppSignupResult }) => void = () => {};
    const signup = vi.fn(() => new Promise<{ ok: true; data: WhatsAppSignupResult }>((resolve) => (finish = resolve)));
    const { actions } = panel(empty(), { connect: { signup, move: vi.fn(async () => ok(fresh)), catalogs: vi.fn(async () => fail(409)) } });
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));
    const dialog = await screen.findByRole("dialog", { name: "Conectar WhatsApp" });
    await user.click(within(dialog).getByRole("radio", { name: /^Cloud API/ }));
    await user.click(within(dialog).getByRole("button", { name: "Conectar" }));
    expect(signup).toHaveBeenCalledWith(expect.objectContaining({ refId: REF, mode: "cloud_api", meta: META }));
    const veil = await screen.findByRole("dialog", { name: "Continúa en la ventana de Meta" });
    expect(within(veil).getByText(/administra Barbería Cultor, elige la cuenta de WhatsApp Business y confirma el número con el código/)).toBeVisible();
    expect(veil.querySelector("[data-brand=whatsapp]")).not.toBeNull();
    finish({ ok: true, data: SIGNED });
    // El alta de la consola deja el número en el cliente: se pasa a este agente.
    await waitFor(() => expect(actions.connect!.move).toHaveBeenCalledWith({ ref: REF, channel: CH3, to: RECEPCION }));
    expect(await screen.findByText("+34 600 11 22 33")).toBeVisible();
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${RECEPCION}?canal=${CH3}`));
    expect(toast.success).toHaveBeenCalledWith("WhatsApp conectado. Configura el canal para que empiece a responder.");
    expect(screen.queryByRole("dialog", { name: "Continúa en la ventana de Meta" })).toBeNull();
  });

  it("si el número ya es de este agente (el principal), no lo pasa", async () => {
    const user = userEvent.setup();
    const reload = vi.fn(async () => ok(empty({ channels: [{ id: CH3, type: "whatsapp", identifier: "+34 600 11 22 33", visible_state: fresh.visible_state }] })));
    const { actions } = panel(empty(), { reload });
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Conectar" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/clients/${REF}/agents/${RECEPCION}?canal=${CH3}`));
    expect(actions.connect!.signup).toHaveBeenCalledWith(expect.objectContaining({ mode: "coexistence" }));
    expect(actions.connect!.move).not.toHaveBeenCalled();
  });

  it("si no se puede pasar a este agente (sin guardar), lo dice y no lleva a ninguna parte", async () => {
    const user = userEvent.setup();
    panel(empty(), { connect: { signup: vi.fn(async () => ({ ok: true as const, data: SIGNED })), move: vi.fn(async () => fail(422, "unknown_target_agent")), catalogs: vi.fn() } });
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Conectar" }));
    await waitFor(() =>
      expect(toast.warning).toHaveBeenCalledWith(
        "+34 600 11 22 33 conectado. Por ahora lo atiende el agente principal. Cuando este agente esté guardado, pásalo aquí desde el ⋯ del número.",
      ),
    );
    expect(router.push).not.toHaveBeenCalled();
  });

  it("el velo dice por qué no se conectó y deja intentarlo de nuevo (§10.2)", async () => {
    const user = userEvent.setup();
    const signup = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, code: "number_in_use", text: "Ese número ya está conectado en otro cliente. Nada ha cambiado." })
      .mockResolvedValueOnce({ ok: false, code: "cancelled", text: "La conexión se canceló antes de terminar." });
    const { baseElement } = panel(empty(), { connect: { signup, move: vi.fn(), catalogs: vi.fn() } });
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Conectar" }));
    const inUse = await screen.findByRole("dialog", { name: "Ese número ya está conectado en otra cuenta" });
    expect(within(inUse).getByText("Ese número ya está conectado en otro cliente. Nada ha cambiado.")).toBeVisible();
    expect(await axeViolations(baseElement)).toEqual([]);
    await user.click(within(inUse).getByRole("button", { name: "Intentar de nuevo" }));
    expect(signup).toHaveBeenCalledTimes(2);
    expect(signup).toHaveBeenLastCalledWith(expect.objectContaining({ mode: "coexistence" }));
    const closed = await screen.findByRole("dialog", { name: "Se cerró la ventana de Meta" });
    expect(within(closed).getByText("No se conectó nada. Puedes volver a intentarlo cuando quieras.")).toBeVisible();
    await user.click(within(closed).getByRole("button", { name: "Cerrar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("«Compartir un enlace» crea el enlace del dueño en ese modo y deja la tarjeta del enlace pendiente (§7.3)", async () => {
    const user = userEvent.setup();
    const { actions } = panel();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("radio", { name: /^Cloud API/ }));
    await user.click(screen.getByRole("button", { name: "Compartir un enlace" }));
    const dialog = await screen.findByRole("dialog", { name: "Enlace para el cliente" });
    expect(within(dialog).getByRole("radio", { name: /Es un número que no usa la app/ })).toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "Atrás" }));
    expect(await screen.findByRole("dialog", { name: "Conectar WhatsApp" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Compartir un enlace" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Enlace para el cliente" })).getByRole("button", { name: "Crear enlace" }));
    expect(actions.ownerLink!.create).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, mode: "cloud_api" });
    expect(screen.getByRole("textbox", { name: "Enlace para el dueño" })).toHaveValue("https://consola.auphere.com/connect/whatsapp/tok_abc");
    expect(screen.queryByRole("button", { name: "Atrás" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Listo, ya lo compartí" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const card = screen.getByRole("region", { name: "Enlace enviado al cliente · WhatsApp" });
    expect(card.querySelector("[data-brand=whatsapp]")).not.toBeNull();
    expect(within(card).getByText("Enlace pendiente · número sin la app")).toBeVisible();
    expect(within(card).getByText(/Cuando el cliente termine en Meta, el canal aparece aquí y te avisamos/)).toBeVisible();
  });

  it("con un enlace pendiente, WhatsApp no abre: avisa que hay que revocarlo", async () => {
    const user = userEvent.setup();
    panel(empty({ pending_link: { id: LINK, mode: "coexistence", expires_at: "2026-11-03T10:00:00Z" } }));
    expect(screen.getByRole("region", { name: "Enlace enviado al cliente · WhatsApp" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Conectar WhatsApp" }));
    expect(toast.warning).toHaveBeenCalledWith("Ya hay un enlace pendiente para este canal. Revócalo para empezar otra conexión.");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("al revocar el enlace pendiente, la tarjeta se va", async () => {
    const user = userEvent.setup();
    const { actions } = panel(empty({ pending_link: { id: LINK, mode: "coexistence", expires_at: "2026-11-03T10:00:00Z" } }));
    await user.click(screen.getByRole("button", { name: "Revocar" }));
    await user.click(within(await screen.findByRole("dialog", { name: "¿Revocar el enlace?" })).getByRole("button", { name: "Revocar" }));
    expect(actions.ownerLink!.revoke).toHaveBeenCalledWith({ ref: REF, agent: RECEPCION, link: LINK });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Enlace enviado al cliente · WhatsApp" })).toBeNull());
  });
});

describe("con canales: la lista (§7.2)", () => {
  it("cada número con el logo de WhatsApp, a quién responde y a quién escala, y «Añadir otro canal» despliega la rejilla", async () => {
    const user = userEvent.setup();
    const { container } = panel(channels(), {}, { pages: { [CH]: page() } });
    const rows = within(screen.getByRole("list", { name: "Números de este agente" })).getAllByRole("listitem");
    expect(rows.map((r) => r.querySelector("[data-slot=brand-logo]")?.getAttribute("data-brand"))).toEqual(["whatsapp", "whatsapp"]);
    expect(within(rows[0]!).getByText("WhatsApp · responde solo a 1 número de prueba · escala a Marta")).toBeVisible();
    expect(within(rows[1]!).getByText("WhatsApp")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Elige un canal" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Añadir otro canal" }));
    expect(screen.getByRole("heading", { level: 2, name: "Elige un canal" })).toHaveFocus();
    const whatsapp = within(grid()).getByRole("button", { name: "Conectar WhatsApp" });
    expect(within(whatsapp).getByText("2 conectados")).toBeVisible();
    expect(within(whatsapp).getByText("Conectar otro número")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Añadir otro canal" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("dice «responde a todos salvo 2 excepciones» y «sin configurar»", () => {
    panel(channels(), {}, {
      pages: {
        [CH]: page({ config: { ...page().config, audience: { mode: "everyone", test_numbers: [], exceptions: ["+34600000001", "+34600000002"] }, escalation: { recipients: [], summary: true } } }),
        "44444444-4444-4444-8444-444444444442": page({ config: { ...page().config, audience: { mode: "unset", test_numbers: [], exceptions: [] }, escalation: { recipients: [], summary: true } } }),
      },
    });
    expect(screen.getByText("WhatsApp · responde a todos salvo 2 excepciones")).toBeVisible();
    expect(screen.getByText("WhatsApp · sin configurar: todavía no responde")).toBeVisible();
  });
});

describe("el logo de WhatsApp en la configuración del canal", () => {
  it("va junto al número, en la cabecera del canal (H5)", () => {
    render(
      <LocaleProvider locale="es">
        <ChannelConfigPage refId={REF} agentId={RECEPCION} page={page()} history={HISTORY} canWrite={false} />
      </LocaleProvider>,
    );
    const header = screen.getByRole("heading", { level: 2, name: "+34 611 20 48 93" }).closest("header") as HTMLElement;
    expect(header.querySelector("[data-brand=whatsapp]")).not.toBeNull();
  });
});

describe("el alta de Meta que ya tiene la consola, con el modo elegido", () => {
  it("abre Meta con la configuración de ese modo y manda lo que devuelve a la API", async () => {
    sdk.loginWithMeta.mockResolvedValueOnce({ code: "c0de", waba_id: "w1", phone_number_id: "p1" });
    sdk.whatsappSignupAction.mockResolvedValueOnce(ok(SIGNED));
    const out = await runWhatsAppSignup({ refId: REF, meta: META, mode: "coexistence", t });
    expect(sdk.loginWithMeta).toHaveBeenCalledWith({ appId: "123", version: "v22.0", configId: "cfg-coex", mode: "coexistence" });
    expect(sdk.whatsappSignupAction).toHaveBeenCalledWith({ ref: REF, mode: "coexistence", code: "c0de", waba_id: "w1", phone_number_id: "p1" });
    expect(out).toEqual({ ok: true, data: SIGNED });
  });

  it("el cupo lleno no enseña el texto en inglés de la API", async () => {
    sdk.loginWithMeta.mockResolvedValueOnce({ code: "c0de", waba_id: "w1" });
    sdk.whatsappSignupAction.mockResolvedValueOnce({ ok: false, status: 409, message: "Channel quota reached: 3 of 3", code: null });
    const out = await runWhatsAppSignup({ refId: REF, meta: META, mode: "cloud_api", t });
    expect(out).toEqual({ ok: false, code: "quota", text: t("channels.proto.error.quota") });
  });
});

describe("spec 049: Instagram y Messenger para un partner con el canal en beta", () => {
  const OFFER = { app_id: "123", graph_version: "v26.0", channels: [{ kind: "instagram" as const, config_id: "cfg-ig" }] };

  it("Instagram se conecta desde su tarjeta y queda en este agente; Messenger sigue sin poder empezar", async () => {
    sdk.loginForCode.mockResolvedValueOnce("CODE");
    sdk.metaSocialConnectAction.mockResolvedValueOnce({
      ok: true,
      data: { status: "connected", channel: { id: CH3, username: "demo.store", display_name: "Demo" }, nonce: null, accounts: [] },
    });
    const { actions } = panel(empty({ meta_social: OFFER }));

    const instagram = within(grid()).getByRole("button", { name: /Instagram/ });
    expect(within(grid()).getAllByRole("button")).toHaveLength(2);
    const cards = within(grid()).getAllByRole("listitem");
    expect(cards[1]!.firstElementChild).toHaveAttribute("aria-disabled", "true");

    await userEvent.click(instagram);

    await waitFor(() => expect(sdk.metaSocialConnectAction).toHaveBeenCalledWith({ ref: REF, kind: "instagram", code: "CODE" }));
    expect(sdk.loginForCode).toHaveBeenCalledWith({ appId: "123", version: "v26.0", configId: "cfg-ig" });
    await waitFor(() => expect(actions.connect!.move).toHaveBeenCalledWith({ ref: REF, channel: CH3, to: RECEPCION }));
    expect(toast.success).toHaveBeenCalledWith("@demo.store conectado. El agente ya atiende sus mensajes.");
  });
});

