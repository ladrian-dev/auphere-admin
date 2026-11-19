import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { InboxAuthor } from "@/lib/backend/inbox";

import { eventText } from "../event-text";

const a = vi.hoisted(() => ({ inboxSettingsAction: vi.fn(), patchInboxSettingsAction: vi.fn() }));
vi.mock("@/app/(console)/inbox/actions", () => a);
const { InboxSettings } = await import("../inbox-settings");
const { t: translate } = await import("@/i18n/messages");

const LABEL = "Cerrar las conversaciones sin mensajes";

function open() {
  render(
    <LocaleProvider locale="es">
      <InboxSettings />
    </LocaleProvider>,
  );
  return userEvent.click(screen.getByRole("button", { name: "Ajustes de la Bandeja" }));
}

beforeEach(() => {
  a.inboxSettingsAction.mockReset();
  a.patchInboxSettingsAction.mockReset();
});

/** Spec 064 (requisito 5.1): the Inbox's one setting, in a dialog off its header. */
describe("Bandeja · ajustes (spec 064)", () => {
  it("does not ask for the settings until the dialog is opened", () => {
    render(
      <LocaleProvider locale="es">
        <InboxSettings />
      </LocaleProvider>,
    );
    expect(a.inboxSettingsAction).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("loading: says so, with the place of the field kept", async () => {
    a.inboxSettingsAction.mockReturnValue(new Promise(() => {}));
    await open();
    const dialog = await screen.findByRole("dialog", { name: "Ajustes de la Bandeja" });
    expect(within(dialog).getByRole("status", { name: "Cargando los ajustes" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("combobox")).toBeNull();
  });

  it("ideal: starts at «Nunca», offers the four terms and says what it closes", async () => {
    a.inboxSettingsAction.mockResolvedValue({ ok: true, data: { autoclose_hours: null } });
    await open();
    const dialog = await screen.findByRole("dialog", { name: "Ajustes de la Bandeja" });
    const term = await within(dialog).findByRole("combobox", { name: LABEL });
    expect(term).toHaveValue("");
    expect(within(term).getAllByRole("option").map((o) => o.textContent)).toEqual(["Nunca", "Tras 24 horas", "Tras 3 días", "Tras 7 días", "Tras 30 días"]);
    expect(within(dialog).getByText(/Solo se cierran las que lleva el agente/)).toBeInTheDocument();
  });

  it("saves at once, says it, and «Nunca» goes back as null", async () => {
    a.inboxSettingsAction.mockResolvedValue({ ok: true, data: { autoclose_hours: 24 } });
    a.patchInboxSettingsAction.mockResolvedValueOnce({ ok: true, data: { autoclose_hours: 168 } });
    await open();
    const term = await screen.findByRole("combobox", { name: LABEL });
    expect(term).toHaveValue("24");
    await userEvent.selectOptions(term, "168");
    await waitFor(() => expect(a.patchInboxSettingsAction).toHaveBeenCalledWith({ autoclose_hours: 168 }));
    expect(await screen.findByText("Guardado.")).toBeInTheDocument();
    expect(term).toHaveValue("168");
    a.patchInboxSettingsAction.mockResolvedValueOnce({ ok: true, data: { autoclose_hours: null } });
    await userEvent.selectOptions(term, "");
    await waitFor(() => expect(a.patchInboxSettingsAction).toHaveBeenLastCalledWith({ autoclose_hours: null }));
  });

  it("a save that fails is said, and the value goes back to what is stored", async () => {
    a.inboxSettingsAction.mockResolvedValue({ ok: true, data: { autoclose_hours: 24 } });
    a.patchInboxSettingsAction.mockResolvedValue({ ok: false, status: 500, message: "boom" });
    await open();
    const term = await screen.findByRole("combobox", { name: LABEL });
    await userEvent.selectOptions(term, "72");
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo guardar. Inténtalo de nuevo.");
    expect(term).toHaveValue("24");
    expect(screen.queryByText("Guardado.")).toBeNull();
  });

  it("error: the settings could not be read, with «Reintentar» and no field to touch", async () => {
    a.inboxSettingsAction.mockResolvedValueOnce({ ok: false, status: 500, message: "boom" });
    await open();
    const dialog = await screen.findByRole("dialog", { name: "Ajustes de la Bandeja" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No pudimos cargar los ajustes.");
    expect(within(dialog).queryByRole("combobox")).toBeNull();
    a.inboxSettingsAction.mockResolvedValueOnce({ ok: true, data: { autoclose_hours: 72 } });
    await userEvent.click(within(dialog).getByRole("button", { name: "Reintentar" }));
    expect(await within(dialog).findByRole("combobox", { name: LABEL })).toHaveValue("72");
  });

  it("opening it again reads the settings again", async () => {
    a.inboxSettingsAction.mockResolvedValue({ ok: true, data: { autoclose_hours: null } });
    await open();
    await screen.findByRole("combobox", { name: LABEL });
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "Ajustes de la Bandeja" }));
    await screen.findByRole("combobox", { name: LABEL });
    expect(a.inboxSettingsAction).toHaveBeenCalledTimes(2);
  });
});

/** Spec 064 (5.2): the thread says a conversation was closed for inactivity. */
describe("Bandeja · «Se cerró por inactividad» (spec 064)", () => {
  const t = (key: string, vars?: Record<string, string | number>) => translate("es", key as never, vars);
  const system: InboxAuthor = { kind: "system", name: null, is_me: false } as InboxAuthor;
  const me: InboxAuthor = { kind: "member", name: "Ana", is_me: true } as InboxAuthor;

  it("a conversation the system closed says why, not who", () => {
    expect(eventText("resolved", system, "inactivity", t as never)).toBe("Se cerró por inactividad");
  });

  it("one resolved by hand reads as before", () => {
    expect(eventText("resolved", me, null, t as never)).toBe("La marcaste como resuelta");
    expect(eventText("resolved", { ...me, is_me: false } as InboxAuthor, null, t as never)).toBe("Ana la marcó como resuelta");
  });
});
