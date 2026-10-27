import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { LinkDetection, NicheSuggestion } from "@/lib/backend/clients-v2";

vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  createClientV2Action: vi.fn(),
  detectClientLinksAction: vi.fn(),
  nicheSuggestionsAction: vi.fn(),
}));

const { ClientModal } = await import("../client-modal");
type Actions = import("../client-modal").ClientModalActions;

/**
 * Spec 047 (T050, historia 3): el modal «Nuevo cliente». Tres datos, los chips
 * de «Irá a la ficha», las sugerencias de nicho, «Más ajustes» con lo deducido
 * y el pie que dice qué falta. Las acciones son de mentira: la API se prueba en
 * `tests/integration/clients/test_create_three_fields.py`.
 */

const ok = <T,>(data: T) => ({ ok: true as const, data });

const CHILE: LinkDetection = {
  links: [
    {
      kind: "web",
      network: "web",
      value: "flor-y-encanto.cl",
      url: "https://flor-y-encanto.cl",
      handle: null,
      target: "website",
      guessed: false,
      alternatives: [],
    },
    {
      kind: "social",
      network: "instagram",
      value: "@florencanto",
      url: "https://www.instagram.com/florencanto",
      handle: "@florencanto",
      target: "links",
      guessed: true,
      alternatives: ["tiktok", "x", "threads", "youtube", "facebook"],
    },
  ],
  deduced: { country: "CL", timezone: "America/Santiago", price_currency: "CLP", wallet_currency: "USD", eu_only: false, source: "web" },
};
const NOTHING: LinkDetection = {
  links: [],
  deduced: { country: null, timezone: "UTC", price_currency: null, wallet_currency: "USD", eu_only: false, source: "default" },
};
const SUGGESTIONS: NicheSuggestion[] = [
  { source: "template", key: "barbershop", group: "beauty", value: null, uses: 0 },
  { source: "template", key: "dental", group: "health", value: null, uses: 0 },
  { source: "used", key: null, group: null, value: "Floristería", uses: 3 },
];

function setup(over: { detect?: Actions["detect"]; create?: Actions["create"] } = {}) {
  const detect = vi.fn<Actions["detect"]>(over.detect ?? (async ({ info }) => ok(info.includes("flor") ? CHILE : NOTHING)));
  const suggest = vi.fn<Actions["suggest"]>(async () => ok(SUGGESTIONS));
  const create = vi.fn<Actions["create"]>(
    over.create ?? (async (body) => ok({ ref: "flor-y-encanto", name: body.name, status: "active" as const, duplicate_name: false, read_job_id: "j1" })),
  );
  const onCreated = vi.fn();
  const onOpenChange = vi.fn();
  const user = userEvent.setup();
  render(
    <LocaleProvider locale="es">
      <ClientModal mode="create" open onOpenChange={onOpenChange} onCreated={onCreated} actions={{ detect, suggest, create }} />
    </LocaleProvider>,
  );
  const dialog = screen.getByRole("dialog", { name: "Nuevo cliente" });
  return { user, dialog, detect, suggest, create, onCreated, onOpenChange };
}

describe("ClientModal · Nuevo cliente", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sin nombre o sin nicho, «Crear cliente» está desactivado y el pie dice por qué", async () => {
    const { user, dialog } = setup();
    const create = within(dialog).getByRole("button", { name: "Crear cliente" });
    expect(create).toBeDisabled();
    expect(within(dialog).getByText("Nombre y nicho son obligatorios")).toBeInTheDocument();
    await user.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Flor y Encanto");
    expect(create).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox", { name: /Nicho/ }), "Florería");
    expect(create).toBeEnabled();
    expect(within(dialog).queryByText("Nombre y nicho son obligatorios")).toBeNull();
  });

  it("lo que se escribe en la información sale como chips con su destino; un @ suelto se puede cambiar de red", async () => {
    const { user, dialog, detect } = setup();
    await user.type(within(dialog).getByRole("textbox", { name: /Información adicional/ }), "flor-y-encanto.cl · @florencanto");
    const list = await within(dialog).findByRole("list", { name: "Enlaces que irán a la ficha" });
    expect(within(dialog).getByText("Irá a la ficha:")).toBeInTheDocument();
    const chips = within(list).getAllByRole("listitem");
    expect(chips.map((c) => c.textContent)).toEqual([
      expect.stringContaining("flor-y-encanto.cl· Web"),
      expect.stringContaining("@florencanto· Redes · Instagram"),
    ]);
    expect(detect).toHaveBeenLastCalledWith(expect.objectContaining({ info: "flor-y-encanto.cl · @florencanto" }));
    const network = within(list).getByRole("combobox", { name: "Red de @florencanto" });
    await user.selectOptions(network, "tiktok");
    expect(within(list).getByText(/Redes · TikTok/)).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Quitar flor-y-encanto.cl" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });

  it("una sugerencia rellena el nicho vacío y, con texto, se añade sin borrar", async () => {
    const { user, dialog } = setup();
    const niche = within(dialog).getByRole("textbox", { name: /Nicho/ });
    await user.click(await within(dialog).findByRole("button", { name: "Añadir «Barbería» al nicho" }));
    expect(niche).toHaveValue("Barbería");
    await user.clear(niche);
    await user.type(niche, "De barrio con 2 sedes");
    await user.click(await within(dialog).findByRole("button", { name: "Añadir «Floristería» al nicho" }));
    expect(niche).toHaveValue("De barrio con 2 sedes · Floristería");
  });

  it("«Más ajustes» propone lo deducido de una web .cl y deja cambiarlo", async () => {
    const { user, dialog } = setup();
    await user.type(within(dialog).getByRole("textbox", { name: /Información adicional/ }), "flor-y-encanto.cl");
    await within(dialog).findByRole("list", { name: "Enlaces que irán a la ficha" });
    const toggle = within(dialog).getByRole("button", { name: "Más ajustes" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(within(dialog).getByText("Deducido de su web. Puedes cambiarlo.")).toBeInTheDocument();
    expect(within(dialog).getByRole("combobox", { name: "País" })).toHaveValue("CL");
    expect(within(dialog).getByRole("combobox", { name: "Zona horaria" })).toHaveValue("America/Santiago");
    expect(within(dialog).getByRole("combobox", { name: /Moneda de los precios/ })).toHaveValue("CLP");
    expect(within(dialog).getByRole("combobox", { name: /Moneda de la bolsa/ })).toHaveValue("USD");
    expect(within(dialog).getByRole("switch", { name: "Solo UE" })).not.toBeChecked();
    // Elegir España propone «Solo UE».
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "País" }), "ES");
    expect(within(dialog).getByRole("switch", { name: "Solo UE" })).toBeChecked();
  });

  it("crear manda los tres datos y lo deducido, con su clave de idempotencia, y avisa a quien abrió", async () => {
    const { user, dialog, create, onCreated } = setup();
    await user.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Flor y Encanto");
    await user.type(within(dialog).getByRole("textbox", { name: /Nicho/ }), "Florería");
    await user.type(within(dialog).getByRole("textbox", { name: /Información adicional/ }), "flor-y-encanto.cl");
    await within(dialog).findByRole("list", { name: "Enlaces que irán a la ficha" });
    await user.click(within(dialog).getByRole("button", { name: "Crear cliente" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ ref: "flor-y-encanto" })));
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Flor y Encanto",
        niche: "Florería",
        info: "flor-y-encanto.cl",
        country: "CL",
        timezone: "America/Santiago",
        price_currency: "CLP",
        wallet_currency: "USD",
        eu_only: false,
        links: null,
        idempotency_key: expect.stringMatching(/^alta-/),
      }),
    );
  });

  it("si la API no crea, lo dice y no cierra", async () => {
    const create = vi.fn(async () => ({ ok: false as const, status: 502, message: "upstream" }));
    const { user, dialog, onCreated } = setup({ create });
    await user.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Flor y Encanto");
    await user.type(within(dialog).getByRole("textbox", { name: /Nicho/ }), "Florería");
    await user.click(within(dialog).getByRole("button", { name: "Crear cliente" }));
    expect(await within(dialog).findByText("No se pudo crear el cliente. Inténtalo de nuevo.")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("si no se pueden revisar los enlaces, lo dice sin bloquear el alta", async () => {
    const detect = vi.fn(async () => ({ ok: false as const, status: 502, message: "upstream" }));
    const { user, dialog } = setup({ detect });
    await user.type(within(dialog).getByRole("textbox", { name: /Información adicional/ }), "cultorbarber.com");
    expect(await within(dialog).findByText(/No pudimos revisar los enlaces ahora/)).toBeInTheDocument();
  });

  it("pasa axe, con «Más ajustes» abierto y con chips", async () => {
    const { user, dialog } = setup();
    await user.type(within(dialog).getByRole("textbox", { name: /Información adicional/ }), "flor-y-encanto.cl · @florencanto");
    await within(dialog).findByRole("list", { name: "Enlaces que irán a la ficha" });
    await user.click(within(dialog).getByRole("button", { name: "Más ajustes" }));
    expect(await axeViolations()).toEqual([]);
    // La lista de zonas IANA del navegador tiene cientos de opciones: axe tarda.
  }, 30_000);
});
