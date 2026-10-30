import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ChannelPage } from "@/lib/backend/channel-config-types";

import { CH, HISTORY, RECEPCION, REF, VENTAS, fail, ok, page } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => router }));
vi.mock("@/app/(console)/clients/[ref]/agents/channel-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  listTemplatesAction: vi.fn(async () => ({ ok: true, data: { items: [], approved: 0, rejected: 0, pending: 0 } })),
}));

const { ChannelConfigPage } = await import("../channel-page");
type Actions = NonNullable<React.ComponentProps<typeof ChannelConfigPage>["actions"]>;

/**
 * Spec 047 (historia 11; requisitos 32 y 33; T115) — la configuración de un
 * canal: guardar con la revisión leída, el conflicto con lo que cambió otra
 * persona, los errores con su arreglo, deshacer durante 10 minutos, el
 * historial con el antes y el después, de qué número salen los avisos y los
 * disparadores del agente en solo lectura. Quien solo lee no ve campos.
 *
 * Como el prototipo (`agente.md` §8, hueco H5; requisito 63.1): dentro del
 * agente, con su cabecera de canal, el índice a la izquierda, dos modos,
 * «Excepciones» solo con «A todos», el escalado en filas de una línea,
 * «Mensaje de espera» e «Historial» en «Más ajustes», y la barra que ofrece
 * activar un canal sin configurar.
 */

const onClose = vi.fn();

function view(p: ChannelPage = page(), over: Partial<Actions> = {}, { canWrite = true, balanceHref = null as string | null } = {}) {
  const actions: Actions = {
    save: vi.fn(async ({ config }) => ok(page({ revision: p.revision + 1, config: { ...config, notify_from: p.config.notify_from }, undo_until: new Date(Date.now() + 600_000).toISOString() }))),
    undo: vi.fn(async () => ok(page({ revision: p.revision + 2 }))),
    reload: vi.fn(async () => ok(page({ revision: 5, config: { ...p.config, wait_message: "Ya vamos" } }))),
    history: vi.fn(async () => ok(HISTORY)),
    menu: {
      move: vi.fn(async () => ok(page({ agent: { id: VENTAS, name: "Ventas" } }))),
      pause: vi.fn(async () => ok(page({ status: "paused", visible_state: { code: "paused", tone: "warn", reason: null }, allowed: ["configure", "move", "resume", "disconnect"] }))),
      resume: vi.fn(async () => ok(page())),
      disconnect: vi.fn(),
    },
    ...over,
  };
  const rendered = render(
    <LocaleProvider locale="es">
      <ChannelConfigPage refId={REF} agentId={RECEPCION} page={p} history={HISTORY} canWrite={canWrite} balanceHref={balanceHref} onClose={onClose} actions={actions} />
    </LocaleProvider>,
  );
  return { ...rendered, actions };
}

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  router.replace.mockClear();
  onClose.mockClear();
});

const openMore = async (user: ReturnType<typeof userEvent.setup>) => {
  const toggle = screen.getByRole("button", { name: /Más ajustes/ });
  if (toggle.getAttribute("aria-expanded") !== "true") await user.click(toggle);
};

describe("la página de un canal", () => {
  it("la cabecera del canal, el índice, dos modos y las secciones; los disparadores del agente en solo lectura; pasa axe (H5)", async () => {
    const { container } = view();
    // Dentro del agente: el título de la página es el del agente; el canal lleva un h2.
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    const head = container.querySelector("[data-slot=channel-head]") as HTMLElement;
    expect(within(head).getByRole("heading", { level: 2, name: "+34 611 20 48 93" })).toBeVisible();
    expect(within(head).getByText("WhatsApp · canal de Recepción")).toBeVisible();
    expect(head.querySelector("[data-brand=whatsapp]")).not.toBeNull();
    // El índice: «Excepciones» solo con «A todos».
    const nav = screen.getByRole("navigation", { name: "Secciones de la configuración" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["A quién responde", "Escalado a personas", "Plantillas de mensaje"]);
    expect(within(nav).getByText("Todo esto es del canal. Si el agente atiende en otro canal, allí tiene su propia configuración.")).toBeVisible();
    for (const name of ["A quién responde", "Escalado a personas", "Comprobaciones"]) {
      expect(screen.getByRole("region", { name })).toBeVisible();
    }
    expect(screen.queryByRole("region", { name: "Excepciones" })).toBeNull();
    // Dos modos, sin «Todavía a nadie».
    const modes = screen.getByRole("radiogroup", { name: "A quién responde" });
    expect(within(modes).getAllByRole("radio").map((r) => r.getAttribute("value"))).toEqual(["team_only", "everyone"]);
    expect(within(modes).getByRole("radio", { name: /Solo mi equipo/ })).toBeChecked();
    expect(screen.getByText(/saldrán del número de avisos de Auphere/)).toBeVisible();
    const triggers = container.querySelector("[data-slot=channel-triggers]") as HTMLElement;
    expect(within(triggers).getByText("Cuando pide hablar con una persona")).toBeVisible();
    expect(within(triggers).getByText("Si pide factura")).toBeVisible();
    expect(within(triggers).getByRole("link", { name: "Cambiarlo en el agente" })).toHaveAttribute("href", `/clients/${REF}/agents/${RECEPCION}#bloque-escalation`);
    expect(screen.getByText("Todo guardado.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("«Excepciones» aparece con «A todos», en su sección y en el índice", async () => {
    const user = userEvent.setup();
    view();
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    expect(screen.getByRole("region", { name: "Excepciones" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Secciones de la configuración" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["A quién responde", "Excepciones", "Escalado a personas", "Plantillas de mensaje"]);
  });

  it("«Mensaje de espera» e «Historial» viven en «Más ajustes»", async () => {
    const user = userEvent.setup();
    view();
    expect(screen.queryByRole("region", { name: "Mensaje de espera" })).toBeNull();
    expect(screen.queryByRole("list", { name: "Historial" })).toBeNull();
    await openMore(user);
    expect(screen.getByRole("region", { name: "Mensaje de espera" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Historial" })).toBeVisible();
  });

  it("el escalado va en filas de una línea: persona, por dónde, su dato y la papelera", async () => {
    const user = userEvent.setup();
    view();
    const escalation = screen.getByRole("region", { name: "Escalado a personas" });
    const first = within(escalation).getByRole("group", { name: "Persona 1" });
    expect(first.className).toMatch(/grid-cols-/);
    expect(within(first).getByRole("textbox", { name: /Nombre/ })).toHaveValue("Marta");
    expect(within(first).getByRole("combobox", { name: "Por dónde" })).toHaveValue("whatsapp");
    expect(within(first).getByRole("textbox", { name: /Su WhatsApp/ })).toHaveValue("+34600000009");
    // La papelera quita a la persona; sin nadie, la conversación sigue llegando a la Bandeja.
    await user.click(within(first).getByRole("button", { name: "Quitar a Marta" }));
    expect(within(escalation).getByText(/Nadie recibe aviso todavía/)).toBeVisible();
  });

  it("un canal sin configurar ofrece «Activar solo para mi equipo», «Activar para todos» y «Decidir luego» (32.9)", async () => {
    const user = userEvent.setup();
    const unset = page({
      visible_state: { code: "unconfigured", tone: "muted", reason: null },
      config: { ...page().config, audience: { mode: "unset", test_numbers: [], exceptions: [] } },
    });
    const { actions } = view(unset);
    const bar = screen.getByRole("region", { name: "Guardar configuración" });
    expect(within(bar).getByText("El canal aún no responde: guarda para activarlo.")).toBeVisible();
    expect(within(screen.getByRole("radiogroup", { name: "A quién responde" })).queryByRole("radio", { checked: true })).toBeNull();
    // «Solo mi equipo» sin números se dice antes de mandar.
    await user.click(within(bar).getByRole("button", { name: "Activar solo para mi equipo" }));
    expect(screen.getByText("«Solo mi equipo» necesita al menos un número de prueba.")).toBeVisible();
    expect(actions.save).not.toHaveBeenCalled();
    const audience = screen.getByRole("region", { name: "A quién responde" });
    await user.type(within(audience).getByRole("textbox", { name: /Número nuevo/ }), "+34 611 20 48 93");
    await user.click(within(audience).getByRole("button", { name: "Añadir a Números de prueba" }));
    await user.click(within(bar).getByRole("button", { name: "Activar solo para mi equipo" }));
    expect(actions.save).toHaveBeenCalledWith(expect.objectContaining({ config: expect.objectContaining({ audience: { mode: "team_only", test_numbers: ["+34611204893"], exceptions: [] } }) }));
    expect(toast.success).toHaveBeenCalledWith("Recepción responde por +34 611 20 48 93 solo a tu equipo.");
  });

  it("«Activar para todos» guarda «A todos», y «Decidir luego» vuelve a la lista sin guardar", async () => {
    const user = userEvent.setup();
    const unset = page({ config: { ...page().config, audience: { mode: "unset", test_numbers: [], exceptions: [] } } });
    const { actions } = view(unset);
    const bar = screen.getByRole("region", { name: "Guardar configuración" });
    await user.click(within(bar).getByRole("button", { name: "Activar para todos" }));
    expect(actions.save).toHaveBeenCalledWith(expect.objectContaining({ config: expect.objectContaining({ audience: { mode: "everyone", test_numbers: [], exceptions: [] } }) }));
    expect(toast.success).toHaveBeenCalledWith("Recepción responde por +34 611 20 48 93 a todos.");
    view(unset);
    await user.click(within(screen.getAllByRole("region", { name: "Guardar configuración" })[1]!).getByRole("button", { name: "Decidir luego" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("configurado: «Guardar» y «Descartar» solo con cambios; «Descartar» vuelve a lo guardado", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    const bar = screen.getByRole("region", { name: "Guardar configuración" });
    expect(within(bar).getByText("Los cambios se aplican al guardar.")).toBeVisible();
    await user.click(within(bar).getByRole("button", { name: "Descartar" }));
    expect(screen.getByRole("radio", { name: /Solo mi equipo/ })).toBeChecked();
    expect(within(bar).queryByRole("button", { name: "Guardar" })).toBeNull();
    expect(actions.save).not.toHaveBeenCalled();
  });

  it("los avisos saldrán de este número si tiene la plantilla aprobada (33.3)", () => {
    view(page({ config: { ...page().config, notify_from: "channel" } }));
    expect(screen.getByText("Los avisos por WhatsApp saldrán de este número.")).toBeVisible();
  });

  it("guarda la configuración entera con la revisión leída, en E.164", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    const exceptions = screen.getByRole("region", { name: "Excepciones" });
    await user.type(within(exceptions).getByRole("textbox", { name: /Número nuevo/ }), "+56 9 1234 5678");
    await user.click(within(exceptions).getByRole("button", { name: "Añadir a Excepciones" }));
    expect(within(exceptions).getByRole("list", { name: "Excepciones" })).toHaveTextContent("+56912345678");
    expect(screen.getByText("Los cambios se aplican al guardar.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(actions.save).toHaveBeenCalledWith({
      ref: REF,
      channel: CH,
      revision: 3,
      config: {
        audience: { mode: "everyone", test_numbers: ["+34611204893"], exceptions: ["+56912345678"] },
        escalation: { summary: true, recipients: [{ name: "Marta", via: "whatsapp", phone_e164: "+34600000009" }] },
        wait_message: null,
      },
    });
    expect(toast.success).toHaveBeenCalledWith("Recepción responde por +34 611 20 48 93 a todos.");
    expect(await screen.findByRole("button", { name: "Deshacer el último cambio" })).toBeVisible();
    expect(actions.history).toHaveBeenCalled();
  });

  it("un número mal escrito o repetido no entra en la lista (32.4)", async () => {
    const user = userEvent.setup();
    view();
    const audience = screen.getByRole("region", { name: "A quién responde" });
    const field = within(audience).getByRole("textbox", { name: /Número nuevo/ });
    await user.type(field, "611 20 48");
    await user.click(within(audience).getByRole("button", { name: "Añadir a Números de prueba" }));
    expect(within(audience).getByText(/«611 20 48» no es un número válido/)).toBeVisible();
    await user.clear(field);
    await user.type(field, "+34 611 20 48 93");
    await user.click(within(audience).getByRole("button", { name: "Añadir a Números de prueba" }));
    expect(within(audience).getByText("Ese número ya está en la lista.")).toBeVisible();
  });

  it("«Solo mi equipo» sin números de prueba se dice antes de mandar", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("button", { name: "Quitar +34611204893" }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(screen.getByText("«Solo mi equipo» necesita al menos un número de prueba.")).toBeVisible();
    expect(actions.save).not.toHaveBeenCalled();
  });

  it("«A todos» sin agente guardado lo dice con su arreglo: guardar el agente", async () => {
    const user = userEvent.setup();
    view(page(), { save: vi.fn(async () => fail(409, "agent_not_published", { fix: "publish_agent", blocking: ["agent_not_published"] })) });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    const error = await screen.findByText(/«A todos» necesita el agente guardado/);
    expect(within(error).getByRole("link", { name: "Guardar el agente" })).toHaveAttribute("href", `/clients/${REF}/agents/${RECEPCION}`);
  });

  it("sin saldo: «Asignar saldo» si se puede, y si no, solo la frase", async () => {
    const user = userEvent.setup();
    const save = vi.fn(async () => fail(409, "bag_empty", { fix: "assign_balance" }));
    const { unmount } = view(page(), { save }, { balanceHref: `/usage?client=${REF}&assign=1` });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("link", { name: "Asignar saldo" })).toHaveAttribute("href", `/usage?client=${REF}&assign=1`);
    unmount();
    view(page(), { save });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText(/Pide a quien gestiona el saldo/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "Asignar saldo" })).toBeNull();
  });

  it("un número que la API no acepta dice cuál", async () => {
    const user = userEvent.setup();
    view(page(), { save: vi.fn(async () => fail(422, "invalid_phone", { value: "+3460" })) });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText(/«\+3460» no es un número válido/)).toBeVisible();
  });

  it("con plantilla de solo administradores, «A todos» no se ofrece y se dice por qué (32.5)", () => {
    view(page({ admin_only_template: true }));
    expect(screen.queryByRole("radio", { name: /A todos/ })).toBeNull();
    expect(screen.getByText(/«A todos» no se puede elegir: este agente viene de una plantilla solo para administradores/)).toBeVisible();
  });

  it("si otra persona guardó antes, dice qué cambió y deja elegir (412)", async () => {
    const user = userEvent.setup();
    const save = vi.fn().mockResolvedValueOnce(fail(412, "revision_conflict", { current: 5, changes: ["wait_message"] })).mockResolvedValue(ok(page({ revision: 6 })));
    const { actions } = view(page(), { save });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Alguien guardó antes que tú")).toBeVisible();
    expect(screen.getByText(/Mientras editabas cambió el mensaje de espera/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Guardar los míos encima" }));
    expect(save).toHaveBeenLastCalledWith(expect.objectContaining({ revision: 5 }));
    expect(actions.reload).not.toHaveBeenCalled();
  });

  it("«Ver lo que hay ahora» descarta lo mío y lee lo de ahora", async () => {
    const user = userEvent.setup();
    const { actions } = view(page(), { save: vi.fn(async () => fail(412, "revision_conflict", { current: 5, changes: [] })) });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await user.click(await screen.findByRole("button", { name: "Ver lo que hay ahora" }));
    expect(actions.reload).toHaveBeenCalledWith({ ref: REF, channel: CH });
    await openMore(user);
    await waitFor(() => expect(screen.getByRole("textbox", { name: /Mensaje/ })).toHaveValue("Ya vamos"));
    expect(screen.getByRole("radio", { name: /Solo mi equipo/ })).toBeChecked();
  });

  it("deshacer durante 10 minutos, y pasado el plazo lo dice", async () => {
    const user = userEvent.setup();
    const undo = vi.fn().mockResolvedValueOnce(ok(page({ revision: 5 }))).mockResolvedValueOnce(fail(409, "undo_window_closed"));
    const open = page({ undo_until: new Date(Date.now() + 300_000).toISOString() });
    const { actions } = view(open, { undo, reload: vi.fn(async () => ok(open)) });
    expect(screen.getByText(/Se puede deshacer hasta las/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Deshacer el último cambio" }));
    expect(actions.undo).toHaveBeenCalledWith({ ref: REF, channel: CH });
    expect(toast.success).toHaveBeenCalledWith("Cambio deshecho.");
    expect(screen.queryByRole("button", { name: "Deshacer el último cambio" })).toBeNull();
  });

  it("el escalado admite hasta 10 personas, cada una con su vía", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    const escalation = screen.getByRole("region", { name: "Escalado a personas" });
    await user.click(within(escalation).getByRole("button", { name: "Añadir persona" }));
    const second = within(escalation).getByRole("group", { name: "Persona 2" });
    await user.type(within(second).getByRole("textbox", { name: /Nombre/ }), "Recepción");
    await user.selectOptions(within(second).getByRole("combobox", { name: "Por dónde" }), "inbox");
    expect(within(second).getByText(/Avisa en la Bandeja a todas las personas del cliente/)).toBeVisible();
    await user.click(within(escalation).getByRole("checkbox", { name: /Incluir un resumen/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(actions.save).toHaveBeenCalledWith(
      expect.objectContaining({
        config: expect.objectContaining({
          escalation: {
            summary: false,
            recipients: [
              { name: "Marta", via: "whatsapp", phone_e164: "+34600000009" },
              { name: "Recepción", via: "inbox", client_user_id: null },
            ],
          },
        }),
      }),
    );
    const ten = Array.from({ length: 10 }, (_, i) => ({ name: `P${i}`, via: "inbox", client_user_id: null }));
    view(page({ config: { ...page().config, escalation: { recipients: ten, summary: true } } }));
    expect(screen.getAllByText("Como mucho 10 personas.")[0]).toBeVisible();
  });

  it("las comprobaciones avisan, y las que impiden «A todos» llevan su arreglo", () => {
    view(
      page({
        checks: [
          { code: "tests_up_to_date", ok: false, level: "warn", fix: "run_tests" },
          { code: "escalation_recipient", ok: false, level: "warn", fix: "add_recipient" },
          { code: "agent_not_published", ok: false, level: "block", fix: "publish_agent" },
        ],
      }),
    );
    const checks = screen.getByRole("list", { name: "Comprobaciones" });
    expect(within(checks).getByRole("link", { name: "Ir a las pruebas" })).toHaveAttribute("href", `/clients/${REF}/agents/${RECEPCION}#agente-pruebas`);
    expect(within(checks).getByRole("link", { name: "Añadir a alguien" })).toHaveAttribute("href", "#canal-escalado");
    expect(within(checks).getByText(/El agente no está guardado/)).toBeVisible();
    expect(within(checks).getByText("Impide «A todos»:")).toBeInTheDocument();
  });

  it("el historial enseña quién, cuándo, el antes y el después", async () => {
    const user = userEvent.setup();
    view();
    await openMore(user);
    const history = screen.getByRole("list", { name: "Historial" });
    expect(within(history).getByText("A quién responde: Todavía a nadie → Solo mi equipo")).toBeVisible();
    expect(within(history).getByText("Al conectar")).toBeVisible();
    expect(within(history).getAllByText(/luis@ladrian.studio/)[0]).toBeVisible();
    // Recorrido UI: el origen («console:») no es de la persona y no se enseña.
    expect(within(history).queryByText(/console:/)).toBeNull();
  });

  it("su ⋯ no repite «Configuración», y pasar el número lleva a su nuevo agente", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("button", { name: "Más acciones de +34 611 20 48 93" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Pasar a otro agente", "Pausar este canal", "Desconectar"]);
    await user.click(within(menu).getByRole("menuitem", { name: "Pasar a otro agente" }));
    const dialog = await screen.findByRole("dialog", { name: "Pasar +34 611 20 48 93 a otro agente" });
    expect(within(dialog).getByRole("radio", { name: "Ventas" })).toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "Pasar el número" }));
    expect(actions.menu!.move).toHaveBeenCalledWith({ ref: REF, channel: CH, to: VENTAS });
    expect(router.replace).toHaveBeenCalledWith(`/clients/${REF}/agents/${VENTAS}?canal=${CH}`);
  });

  it("quien solo lee lo ve todo como texto, sin campos ni botones (§V)", () => {
    view(page({ allowed: [] }), {}, { canWrite: false });
    expect(screen.getByText("Tu rol solo permite ver esta configuración.")).toBeVisible();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    // Solo «Más ajustes», para leer el mensaje de espera y el historial.
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([expect.stringMatching(/^Más ajustes/)]);
    expect(screen.getByText("Marta")).toBeVisible();
    expect(screen.getByText("+34611204893")).toBeVisible();
  });
});

describe("la cuenta en Meta (spec 050, 4.1, 4.2, 4.4 y 8.4)", () => {
  const account = {
    verified_name: "Barbería Cultor",
    name_status: "APPROVED",
    name_decision: "REJECTED",
    requested_name: "Barbería Cultor SL",
    name_rejection_reason: "NAME_FORMAT_UNACCEPTABLE",
    username: "barberiacultor",
    username_status: "approved",
    quality_rating: "YELLOW",
    messaging_limit: "TIER_2K",
    account_review: "REJECTED",
    alerts: [{ type: "INCREASED_CAPABILITIES_ELIGIBILITY_FAILED", severity: "CRITICAL", status: "ACTIVE", at: null }],
  };

  it("enseña el nombre y la decisión de Meta, el usuario, la calidad, el límite, la revisión y las alertas", async () => {
    const { container } = view(page({ whatsapp: account }));
    const region = screen.getByRole("region", { name: "La cuenta en Meta" });
    expect(within(region).getByText("Meta rechazó «Barbería Cultor SL». Motivo: Name format unacceptable")).toBeVisible();
    expect(within(region).getByText("@barberiacultor")).toBeVisible();
    expect(within(region).getByText("Media")).toBeVisible();
    expect(within(region).getByText(/2\.?000 personas al día/)).toBeVisible();
    expect(within(region).getByText("Rechazada")).toBeVisible();
    expect(within(region).getByText("Crítica")).toBeVisible();
    expect(within(region).getByText("Increased capabilities eligibility failed")).toBeVisible();
    expect(screen.getByRole("link", { name: "La cuenta en Meta" })).toHaveAttribute("href", "#canal-cuenta");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("un nombre en revisión y un usuario pendiente lo dicen", () => {
    view(page({ whatsapp: { ...account, name_decision: "PENDING", username_status: "pending", alerts: [] } }));
    expect(screen.getByText("«Barbería Cultor SL», en revisión en Meta")).toBeVisible();
    expect(screen.getByText("@barberiacultor, pendiente en Meta")).toBeVisible();
  });

  it("sin nada que decir, la sección no aparece", () => {
    const empty = Object.fromEntries(Object.keys(account).map((k) => [k, k === "alerts" ? [] : null])) as unknown as typeof account;
    view(page({ whatsapp: empty }));
    expect(screen.queryByRole("region", { name: "La cuenta en Meta" })).toBeNull();
    view(page({ whatsapp: null }));
    expect(screen.queryAllByRole("region", { name: "La cuenta en Meta" })).toHaveLength(0);
  });
});
