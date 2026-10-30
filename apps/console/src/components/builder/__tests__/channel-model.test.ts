import { describe, expect, it } from "vitest";

import { t as translate } from "@/i18n/messages";
import type { MessageKey } from "@/i18n/messages";

import {
  addNumber,
  agentChannelsTabHref,
  channelHref,
  channelMenuItems,
  channelStateText,
  checkText,
  conflictSections,
  draftFromPage,
  draftProblem,
  fixLink,
  historyLines,
  isDirty,
  normalizeNumber,
  ownerLinkCopy,
  saveErrorOf,
  toPayload,
} from "../channel-model";
import { businessLineKey, isWebAddress, retestKey, sourceKindKey, teachProblem, visibleSources } from "../knowledge-model";

import { CH, HISTORY, RECEPCION, REF, page, source } from "./channel-fixtures";

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);

/**
 * Spec 047 (T115, T134) — los canales y el conocimiento de un agente sin pintar:
 * el estado visible con las palabras de `events.md` §1.2, el ⋯ solo con lo
 * permitido, los números en formato internacional y sin duplicados (32.4), las
 * palabras de cada error, el historial con su antes y su después, y lo que
 * pide «Enseñar» (37.3).
 */
describe("el estado visible de un canal", () => {
  it("dice lo mismo que en toda la consola, con el motivo de los problemas", () => {
    expect(channelStateText(t, { code: "team_only", tone: "info", reason: null })).toBe("Solo mi equipo");
    expect(channelStateText(t, { code: "everyone", tone: "positive", reason: null })).toBe("A todos");
    expect(channelStateText(t, { code: "unconfigured", tone: "muted", reason: null })).toBe("Sin configurar");
    expect(channelStateText(t, { code: "pending_link", tone: "info", reason: null })).toBe("Pendiente · enlace enviado");
    expect(channelStateText(t, { code: "problem", tone: "danger", reason: "coexistence_inactive" })).toBe("Con problemas · la app lleva días sin abrirse");
    expect(channelStateText(t, { code: "problem", tone: "danger", reason: "otro" })).toBe("Con problemas · sin motivo");
    expect(channelStateText(t, { code: "nuevo", tone: "muted", reason: null })).toBe("nuevo");
  });
});

describe("el ⋯ y las rutas", () => {
  it("solo lo permitido, en el orden de 34.1, y sin «Configuración» en su propia página", () => {
    expect(channelMenuItems(["disconnect", "pause", "configure", "move"])).toEqual(["configure", "move", "pause", "disconnect"]);
    expect(channelMenuItems(["configure", "resume"], { here: true })).toEqual(["resume"]);
    expect(channelMenuItems([])).toEqual([]);
  });

  it("la configuración de un canal se abre dentro de su agente, en la pestaña Canales (63.1)", () => {
    expect(channelHref(REF, RECEPCION, CH)).toBe(`/clients/${REF}/agents/${RECEPCION}?canal=${CH}`);
    expect(agentChannelsTabHref(REF, RECEPCION)).toBe(`/clients/${REF}/agents/${RECEPCION}?tab=channels`);
  });
});

describe("los números (32.4)", () => {
  it("se guardan en E.164, sin espacios ni duplicados", () => {
    expect(normalizeNumber("+34 611 20 48 93")).toBe("+34611204893");
    expect(normalizeNumber("0034 611-20-48-93")).toBe("+34611204893");
    expect(normalizeNumber("(+56) 9 1234 5678")).toBe("+56912345678");
    expect(normalizeNumber("611204893")).toBeNull();
    expect(normalizeNumber("+0611204893")).toBeNull();
    expect(addNumber([], "+34 611 20 48 93")).toEqual({ ok: true, list: ["+34611204893"] });
    expect(addNumber(["+34611204893"], "0034611204893")).toEqual({ ok: false, error: "duplicate" });
    expect(addNumber([], "hola")).toEqual({ ok: false, error: "invalid" });
  });
});

describe("el borrador de la configuración", () => {
  it("parte de la página sin «notify_from», sabe si hay cambios y manda cada vía con su dato", () => {
    const saved = draftFromPage(page());
    expect(saved).not.toHaveProperty("notify_from");
    const draft = {
      ...saved,
      escalation: {
        summary: false,
        recipients: [
          { name: " Marta ", via: "whatsapp", phone_e164: "+34 600 000 009", email: "x@y.z", client_user_id: null },
          { name: "Recepción", via: "inbox", phone_e164: "", email: null, client_user_id: null },
          { name: "Luis", via: "email", phone_e164: "+34600", email: " luis@ladrian.studio ", client_user_id: null },
        ],
      },
      wait_message: "  ",
    };
    expect(isDirty(saved, draftFromPage(page()))).toBe(false);
    expect(isDirty(draft, saved)).toBe(true);
    expect(toPayload(draft)).toEqual({
      audience: saved.audience,
      escalation: {
        summary: false,
        recipients: [
          { name: "Marta", via: "whatsapp", phone_e164: "+34600000009" },
          { name: "Recepción", via: "inbox", client_user_id: null },
          { name: "Luis", via: "email", email: "luis@ladrian.studio" },
        ],
      },
      wait_message: null,
    });
  });

  it("dice antes de mandar lo que la API rechazaría", () => {
    const base = draftFromPage(page());
    expect(draftProblem(t, { ...base, audience: { ...base.audience, test_numbers: [] } })?.text).toBe("«Solo mi equipo» necesita al menos un número de prueba.");
    expect(draftProblem(t, { ...base, escalation: { ...base.escalation, recipients: [{ name: "", via: "inbox" }] } })?.section).toBe("escalation");
    expect(draftProblem(t, { ...base, escalation: { ...base.escalation, recipients: [{ name: "Marta", via: "whatsapp", phone_e164: "" }] } })?.text).toBe(
      "Escribe el WhatsApp de Marta.",
    );
    expect(draftProblem(t, { ...base, escalation: { ...base.escalation, recipients: [{ name: "Luis", via: "email", email: "luis@" }] } })?.text).toBe(
      "El correo de Luis no es válido.",
    );
    const eleven = Array.from({ length: 11 }, (_, i) => ({ name: `P${i}`, via: "inbox" }));
    expect(draftProblem(t, { ...base, escalation: { ...base.escalation, recipients: eleven } })?.text).toBe("Como mucho 10 personas.");
    expect(draftProblem(t, { ...base, wait_message: "x".repeat(501) })?.section).toBe("wait");
    expect(draftProblem(t, base)).toBeNull();
  });
});

describe("los errores al guardar (console-api.md §9)", () => {
  it("cada código dice su frase, en su sección, con su arreglo", () => {
    expect(saveErrorOf(t, { status: 422, code: "invalid_phone", info: { value: "+3461" } })).toEqual({
      section: "general",
      text: "«+3461» no es un número válido. Escríbelo con el prefijo del país, por ejemplo +34 611 20 48 93.",
      fix: null,
    });
    expect(saveErrorOf(t, { status: 409, code: "agent_not_published", info: { fix: "publish_agent" } })).toMatchObject({ section: "audience", fix: "publish_agent" });
    expect(saveErrorOf(t, { status: 409, code: "bag_empty", info: { fix: "assign_balance" } })).toMatchObject({ fix: "assign_balance" });
    expect(saveErrorOf(t, { status: 422, code: "too_many_recipients" }).text).toBe("Como mucho 10 personas.");
    expect(saveErrorOf(t, { status: 422, code: "channel_test_numbers_required" }).section).toBe("audience");
    expect(saveErrorOf(t, { status: 409, code: "audience_admin_only_template" }).fix).toBeNull();
    expect(saveErrorOf(t, { status: 403 }).text).toBe(t("common.forbidden"));
    expect(saveErrorOf(t, { status: 500 }).text).toBe("No se pudo guardar. Inténtalo de nuevo.");
  });

  it("el arreglo es un enlace solo si se puede hacer aquí", () => {
    const targets = { agent: "/a", tests: "/a#agente-pruebas", balance: null, recipients: "#canal-escalado" };
    expect(fixLink("publish_agent", targets)).toEqual({ href: "/a", label: "builder.channel.fix.publish_agent" });
    expect(fixLink("assign_balance", targets)).toBeNull();
    expect(fixLink("assign_balance", { ...targets, balance: "/usage?client=x&assign=1" })?.href).toBe("/usage?client=x&assign=1");
    expect(fixLink("run_tests", targets)?.href).toBe("/a#agente-pruebas");
    expect(fixLink("add_recipient", targets)?.href).toBe("#canal-escalado");
    expect(fixLink(null, targets)).toBeNull();
  });

  it("el conflicto dice qué cambió otra persona", () => {
    expect(conflictSections(t, ["audience", "escalation"])).toBe("a quién responde y el escalado");
    expect(conflictSections(t, ["wait_message"])).toBe("el mensaje de espera");
    expect(conflictSections(t, [])).toBe("la configuración");
  });
});

describe("las comprobaciones y el historial", () => {
  it("cada comprobación con su frase", () => {
    expect(checkText(t, { code: "tests_up_to_date", ok: false, level: "warn", fix: "run_tests" })).toBe("Hay pruebas sin pasar o que fallan.");
    expect(checkText(t, { code: "bag_empty", ok: false, level: "block", fix: "assign_balance" })).toMatch(/no tiene saldo/);
    expect(checkText(t, { code: "x", ok: false, level: "warn", fix: null })).toBe("Comprobación: x");
  });

  it("el historial enseña el antes y el después de lo que cambió", () => {
    expect(historyLines(t, HISTORY[0]!)).toEqual([
      "A quién responde: Todavía a nadie → Solo mi equipo",
      "Números de prueba: ninguno → 1 número",
      "Personas a las que avisar: nadie → 1 persona",
    ]);
    expect(historyLines(t, { before: { wait_message: null }, after: { wait_message: "Ya vamos" } })).toEqual(["Mensaje de espera: sin mensaje → con mensaje"]);
    expect(historyLines(t, { before: HISTORY[0]!.after, after: HISTORY[0]!.after })).toEqual([]);
  });
});

describe("el enlace del dueño (31.3)", () => {
  it("«desde su teléfono» solo con la bandera", () => {
    expect(t(ownerLinkCopy(false).body)).not.toMatch(/desde su teléfono/);
    expect(t(ownerLinkCopy(false).message, { url: "u" })).not.toMatch(/teléfono/);
    expect(t(ownerLinkCopy(true).body)).toMatch(/desde su teléfono/);
    expect(t("ch.link.title")).not.toMatch(/teléfono/);
  });

  it("ninguna frase de la consola promete «sin Facebook»", () => {
    for (const key of ["builder.ownerLink.mode.whatsapp_login", "builder.ownerLink.mode.whatsapp_login.hint", "ch.connect.mode.whatsapp_login"] as const) {
      expect(t(key)).not.toMatch(/facebook/i);
    }
  });
});

describe("el conocimiento de un agente (37.3, 12.2)", () => {
  it("las vivas y las quitadas que aún se recuperan; las demás no se ven", () => {
    const now = Date.parse("2026-10-27T10:00:00Z");
    const live = source();
    const restorable = source({ id: "r", removed_at: "2026-10-27T09:55:00Z", restore_until: "2026-10-27T10:05:00Z" });
    const gone = source({ id: "g", removed_at: "2026-10-27T09:00:00Z", restore_until: "2026-10-27T09:10:00Z" });
    expect(visibleSources([live, restorable, gone], now)).toEqual({ live: [live], restorable: [restorable] });
  });

  it("«Enseñar» pide el texto y siempre el alcance, y dice qué pruebas se vuelven a pasar", () => {
    expect(teachProblem("  ", "agent")).toBe("builder.teach.required.text");
    expect(teachProblem("Cerramos en agosto", null)).toBe("builder.teach.required.scope");
    expect(teachProblem("x".repeat(5001), "agent")).toBe("builder.teach.tooLong");
    expect(teachProblem("Cerramos en agosto", "business")).toBeNull();
    expect(t(retestKey("agent"))).toMatch(/de este agente/);
    expect(t(retestKey("business"))).toMatch(/todos los agentes/);
  });

  it("palabras de cada tipo y de las fuentes del negocio", () => {
    expect(t(sourceKindKey("note"))).toBe("Enseñado");
    expect(t(sourceKindKey("url"))).toBe("Web");
    expect(t(businessLineKey(0))).toMatch(/aún no tiene/);
    expect(t(businessLineKey(1), { n: 1 })).toMatch(/1 fuente del negocio/);
    expect(t(businessLineKey(3), { n: 3 })).toMatch(/3 fuentes del negocio/);
    expect(isWebAddress("https://cultor.es/precios")).toBe(true);
    expect(isWebAddress("cultor.es")).toBe(false);
  });
});
