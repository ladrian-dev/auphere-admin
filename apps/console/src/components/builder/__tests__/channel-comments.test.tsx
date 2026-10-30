import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ChannelPage } from "@/lib/backend/channel-config-types";

import { RECEPCION, REF, fail, ok, page } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agents/channel-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({}));

const { ChannelConfigPage } = await import("../channel-page");
type Actions = NonNullable<React.ComponentProps<typeof ChannelConfigPage>["actions"]>;

/**
 * Spec 049 (historia 3) y QA 2026-10-30 (INC-07): la respuesta pública a un
 * comentario de Instagram no salía nunca porque nadie podía escribirla. La
 * página de un canal de Instagram tiene ahora su sección «Comentarios», que
 * guarda al pulsar; los demás canales no la tienen.
 */

const instagram = (over: Partial<ChannelPage> = {}) =>
  page({ type: "instagram", identifier: "@demo.store", instagram_comments: { enabled: true, public_reply: null }, ...over });

function view(p: ChannelPage, comments: Actions["comments"], canWrite = true) {
  const actions: Actions = {
    save: vi.fn(),
    undo: vi.fn(),
    reload: vi.fn(),
    history: vi.fn(async () => ok([])),
    comments,
  };
  return render(
    <LocaleProvider locale="es">
      <ChannelConfigPage refId={REF} agentId={RECEPCION} page={p} history={[]} canWrite={canWrite} actions={actions} />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("los comentarios de un canal de Instagram", () => {
  it("se guarda la respuesta pública al pulsar, con el nombre del canal en la cabecera; pasa axe", async () => {
    const user = userEvent.setup();
    const comments = vi.fn(async () => ok(instagram({ instagram_comments: { enabled: true, public_reply: "Te escribimos por privado" } })));
    const { container } = view(instagram(), comments);

    expect(screen.getByText(/^Instagram/)).toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Comentarios" });
    const save = screen.getByRole("button", { name: "Guardar comentarios" });
    expect(save).toBeDisabled();

    await user.type(screen.getByLabelText(/Respuesta pública/), "  Te escribimos por privado  ");
    await user.click(save);

    expect(comments).toHaveBeenCalledWith({ ref: REF, channel: expect.any(String), enabled: true, public_reply: "Te escribimos por privado" });
    expect(toast.success).toHaveBeenCalledWith("Comentarios guardados.");
    expect(section).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("si la API falla lo dice y no da por guardado", async () => {
    const user = userEvent.setup();
    const comments = vi.fn(async () => fail(409, "not_instagram"));
    view(instagram(), comments);
    await user.click(screen.getByRole("checkbox", { name: /Atender los comentarios/ }));
    await user.click(screen.getByRole("button", { name: "Guardar comentarios" }));
    expect(comments).toHaveBeenCalledWith(expect.objectContaining({ enabled: false, public_reply: null }));
    expect(toast.error).toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("quien solo lee lo ve como texto, y WhatsApp no tiene la sección", () => {
    const { unmount } = view(instagram({ instagram_comments: { enabled: false, public_reply: null } }), vi.fn(), false);
    expect(screen.queryByRole("button", { name: "Guardar comentarios" })).toBeNull();
    expect(screen.getByText("Ninguna")).toBeInTheDocument();
    unmount();
    view(page(), vi.fn());
    expect(screen.queryByRole("region", { name: "Comentarios" })).toBeNull();
  });
});
