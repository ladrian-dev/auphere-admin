import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { messages } from "@/i18n/messages";

import { CatalogPickerBody, catalogFailureKey, manualDeclarationOffered, offerCatalogAfterSignup, replacementNeeded, validCatalogId } from "../catalog-picker";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  listCatalogsAction: vi.fn(),
  setCatalogAction: vi.fn(),
}));

const FLORES = { id: "CAT_FLORES", name: "Flores y ramos", product_count: 12 };
const PLANTAS = { id: "CAT_PLANTAS", name: "Plantas", product_count: null };

function pintar(props: Partial<React.ComponentProps<typeof CatalogPickerBody>> = {}) {
  const onChoose = vi.fn();
  render(
    <LocaleProvider locale="es">
      <CatalogPickerBody state={{ kind: "ready", items: [FLORES, PLANTAS], linkedId: null }} current={null} busy={false} onChoose={onChoose} {...props} />
    </LocaleProvider>,
  );
  return onChoose;
}

describe("El selector de catálogo (spec 022, Historia 1)", () => {
  it("lista los catálogos con su nombre y cuántos productos tienen", () => {
    const onChoose = pintar();
    expect(screen.getByText("Flores y ramos")).toBeInTheDocument();
    expect(screen.getByText("12 productos")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Plantas"));
    expect(onChoose).toHaveBeenCalledWith(PLANTAS);
  });

  it("el que ya está conectado se marca y no se puede volver a elegir", () => {
    pintar({ current: { id: "CAT_FLORES", name: "Flores y ramos", checked_at: null } });
    const conectado = screen.getByText("Flores y ramos").closest("button");
    expect(conectado).toHaveAttribute("aria-current", "true");
    expect(conectado).toBeDisabled();
    expect(screen.getByText("Conectado ahora")).toBeInTheDocument();
  });

  it("sin catálogos: dice que no hay y dónde se crean, no una lista vacía", () => {
    pintar({ state: { kind: "ready", items: [], linkedId: null } });
    expect(screen.getByText("Tu negocio no tiene catálogos")).toBeInTheDocument();
    expect(screen.getByText(/Commerce Manager/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("un rechazo tiene su frase; uno desconocido, la genérica", () => {
    pintar({ state: { kind: "error", code: "catalog_permission_missing", message: null } });
    expect(screen.getByRole("alert")).toHaveTextContent(/vuelve a conectar el número/i);
    expect(catalogFailureKey("catalog_not_owned")).toBe("ch.catalog.err.catalog_not_owned");
    expect(catalogFailureKey("meta_unavailable")).toBe("ch.catalog.err.meta_unavailable");
    expect(catalogFailureKey("channel_has_no_credentials")).toBe("ch.catalog.err.channel_has_no_credentials");
    expect(catalogFailureKey("made_up")).toBeNull();
  });

  it("cambiar de catálogo pide confirmar; conectar el primero, no (Q3)", () => {
    expect(replacementNeeded(null, "CAT_FLORES")).toBe(false);
    expect(replacementNeeded({ id: "CAT_FLORES", name: null, checked_at: null }, "CAT_FLORES")).toBe(false);
    expect(replacementNeeded({ id: "CAT_FLORES", name: null, checked_at: null }, "CAT_PLANTAS")).toBe(true);
    // Y la confirmación nombra al que sale y al que entra.
    expect(messages["ch.catalog.replace.body"].es).toMatch(/\{to\}/);
    expect(messages["ch.catalog.replace.title"].es).toMatch(/\{from\}.*\{to\}/);
  });
});

describe("La oferta al terminar el alta (spec 022, Historia 2)", () => {
  it("se abre solo si el negocio tiene al menos un catálogo", () => {
    expect(offerCatalogAfterSignup({ ok: true, data: { items: [FLORES], linked_id: null } })).toBe(true);
    expect(offerCatalogAfterSignup({ ok: true, data: { items: [], linked_id: null } })).toBe(false);
  });

  it("un permiso que falta o un Meta caído no abren nada ni rompen el alta", () => {
    expect(offerCatalogAfterSignup({ ok: false, status: 409, code: "catalog_permission_missing", message: "" })).toBe(false);
    expect(offerCatalogAfterSignup({ ok: false, status: 503, code: "meta_unavailable", message: "" })).toBe(false);
    expect(messages["ch.catalog.picker.later"].es).toBe("Ahora no");
    expect(messages["ch.catalog.offer.help"].es).toMatch(/más tarde desde la tarjeta/i);
  });
});

describe("Apuntar el catálogo a mano en coexistencia (spec 022, iteración 4)", () => {
  it("se ofrece solo en coexistencia y solo cuando Meta no listó", () => {
    expect(manualDeclarationOffered(true, { kind: "error" })).toBe(true);
    expect(manualDeclarationOffered(true, { kind: "ready" })).toBe(false);
    expect(manualDeclarationOffered(true, { kind: "loading" })).toBe(false);
    expect(manualDeclarationOffered(false, { kind: "error" })).toBe(false);
    expect(validCatalogId("1605043874367785")).toBe(true);
    expect(validCatalogId(" 1605043874367785 ")).toBe(true);
    expect(validCatalogId("CAT_FLORES")).toBe(false);
    expect(validCatalogId("12")).toBe(false);
  });

  it("con el permiso ausente en coexistencia enseña el formulario, no el error", () => {
    const onDeclare = vi.fn();
    render(
      <LocaleProvider locale="es">
        <CatalogPickerBody
          state={{ kind: "error", code: "catalog_permission_missing", message: null }}
          current={null}
          busy={false}
          onChoose={vi.fn()}
          coexistence
          onDeclare={onDeclare}
        />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(/Commerce Manager/)).toBeInTheDocument();
    const id = screen.getByLabelText(/Identificador del catálogo/);
    const name = screen.getByLabelText(/Nombre/);
    fireEvent.change(id, { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Apuntar catálogo" }));
    expect(screen.getByRole("alert")).toHaveTextContent("solo cifras");
    expect(onDeclare).not.toHaveBeenCalled();
    fireEvent.change(id, { target: { value: " 1605043874367785 " } });
    fireEvent.change(name, { target: { value: "Catálogo de Flor y Encanto 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Apuntar catálogo" }));
    expect(onDeclare).toHaveBeenCalledWith("1605043874367785", "Catálogo de Flor y Encanto 2");
  });

  it("fuera de coexistencia el permiso ausente sigue siendo una frase", () => {
    render(
      <LocaleProvider locale="es">
        <CatalogPickerBody state={{ kind: "error", code: "catalog_permission_missing", message: null }} current={null} busy={false} onChoose={vi.fn()} onDeclare={vi.fn()} />
      </LocaleProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/vuelve a conectar/i);
  });
});
