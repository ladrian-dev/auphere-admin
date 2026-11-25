import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { TemplateComposer } from "../template-composer";

const createTemplateAction = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  createTemplateAction: (...args: unknown[]) => createTemplateAction(...args),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function mount(locale: "es" | "en" = "es") {
  return render(
    <LocaleProvider locale={locale}>
      <TemplateComposer refId="demo" open onOpenChange={vi.fn()} />
    </LocaleProvider>,
  );
}

const body = () => screen.getByLabelText("Texto del mensaje") as HTMLTextAreaElement;
const send = () => screen.getByRole("button", { name: "Enviar a Meta para revisión" });

describe("Nueva plantilla de WhatsApp", () => {
  it("explica para qué sirve cada categoría y empieza en Utilidad", () => {
    mount();
    const utility = screen.getByRole("radio", { name: /Utilidad/ });
    expect(utility).toBeChecked();
    expect(utility.closest("label")).toHaveTextContent("Meta la aprueba antes y cuesta menos.");
    expect(screen.getByRole("radio", { name: /Marketing/ })).not.toBeChecked();
    // Spec 077 (3.4): Autenticación vuelve, ahora con el formato fijo de Meta.
    expect(screen.getByRole("radio", { name: /Autenticaci/ })).not.toBeChecked();
  });

  it("con Autenticación pide botón, caducidad y aviso en lugar del mensaje, y enseña el texto fijo de Meta", async () => {
    createTemplateAction.mockReset();
    createTemplateAction.mockResolvedValue({ ok: true, data: { id: "T2", name: "tecfin_codigo", status: "PENDING", category: "AUTHENTICATION" } });
    mount();
    fireEvent.click(screen.getByRole("radio", { name: /Autenticaci/ }));
    expect(screen.queryByLabelText("Texto del mensaje")).toBeNull();
    expect(screen.queryByRole("button", { name: "Añadir botón" })).toBeNull();
    expect(screen.getByLabelText("Texto del botón")).toHaveValue("Copiar código");
    const preview = screen.getByLabelText("Así lo verá el cliente");
    expect(preview).toHaveTextContent("123456 es tu código de verificación. Por tu seguridad, no lo compartas.");
    expect(preview).toHaveTextContent("Este código caduca en 10 minutos.");

    fireEvent.click(screen.getByLabelText(/Aviso de seguridad/));
    expect(preview).not.toHaveTextContent("Por tu seguridad");
    fireEvent.change(screen.getByLabelText("Caduca en (min)"), { target: { value: "" } });
    expect(preview).not.toHaveTextContent("caduca");

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "tecfin_codigo" } });
    fireEvent.click(send());
    await waitFor(() => expect(createTemplateAction).toHaveBeenCalled());
    expect(createTemplateAction.mock.calls[0]?.[0]).toEqual({
      ref: "demo",
      name: "tecfin_codigo",
      language: "es",
      category: "AUTHENTICATION",
      otp_button_text: "Copiar código",
      otp_security_recommendation: false,
    });
  });

  it("con Autenticación enseña el texto fijo solo si la plantilla es en español, y lo dice", () => {
    mount();
    fireEvent.click(screen.getByRole("radio", { name: /Autenticaci/ }));
    const preview = screen.getByLabelText("Así lo verá el cliente");
    expect(preview).toHaveTextContent("Vista previa en español");
    fireEvent.change(screen.getByLabelText("Idioma"), { target: { value: "en" } });
    expect(preview).not.toHaveTextContent("es tu código de verificación");
    expect(preview).toHaveTextContent("Meta pone el texto fijo en English, el idioma de la plantilla.");
    fireEvent.change(screen.getByLabelText("Idioma"), { target: { value: "es_MX" } });
    expect(preview).toHaveTextContent("123456 es tu código de verificación.");
  });

  it("con la consola en inglés, la plantilla en español se previsualiza en español", () => {
    mount("en");
    fireEvent.click(screen.getByRole("radio", { name: /Authentication/ }));
    const preview = screen.getByLabelText("What the customer will see");
    expect(preview).toHaveTextContent("Preview in Spanish");
    expect(preview).toHaveTextContent("123456 es tu código de verificación. Por tu seguridad, no lo compartas.");
    expect(preview).not.toHaveTextContent("is your verification code");
  });

  it("con Autenticación no envía una caducidad fuera de 1 a 90", () => {
    createTemplateAction.mockReset();
    mount();
    fireEvent.click(screen.getByRole("radio", { name: /Autenticaci/ }));
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "codigo" } });
    fireEvent.change(screen.getByLabelText("Caduca en (min)"), { target: { value: "120" } });
    expect(screen.getByLabelText("Caduca en (min)")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Falta una caducidad de 1 a 90 minutos.")).toBeInTheDocument();
    fireEvent.click(send());
    expect(createTemplateAction).not.toHaveBeenCalled();
  });

  it("convierte el nombre al formato de Meta mientras se escribe", () => {
    mount();
    const name = screen.getByLabelText("Nombre");
    fireEvent.change(name, { target: { value: "Aviso de Pago" } });
    expect(name).toHaveValue("aviso_de_pago");
  });

  it("dice qué falta y, al enviar incompleta, marca y enfoca el primer campo", async () => {
    mount();
    expect(send()).toBeEnabled();
    expect(screen.getByText("Falta el nombre, el texto del mensaje.")).toBeInTheDocument();
    fireEvent.click(send());
    const name = screen.getByLabelText("Nombre");
    expect(name).toHaveAttribute("aria-invalid", "true");
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(name).toHaveFocus();
  });

  it("inserta una variable, pide su ejemplo y lo pinta en la vista previa", () => {
    mount();
    fireEvent.change(body(), { target: { value: "Hola , tu pedido sale hoy." } });
    body().setSelectionRange(5, 5);
    fireEvent.click(screen.getByRole("button", { name: "{{nombre}}" }));
    expect(body().value).toBe("Hola {{nombre}}, tu pedido sale hoy.");
    const example = screen.getByLabelText("Ejemplo de nombre");
    fireEvent.change(example, { target: { value: "Camila" } });
    const preview = screen.getByLabelText("Así lo verá el cliente");
    expect(preview).toHaveTextContent("Hola Camila, tu pedido sale hoy.");
  });

  it("avisa de lo que Meta rechaza en el texto, bajo el propio campo", () => {
    mount();
    fireEvent.change(body(), { target: { value: "{{nombre}}, tu pedido es el {{pedido}}" } });
    expect(screen.getByText(/no puede empezar con una variable/)).toBeInTheDocument();
    expect(screen.getByText(/no puede terminar con una variable/)).toBeInTheDocument();
  });

  it("envía el nombre limpio, el texto, los botones y un ejemplo por variable", async () => {
    createTemplateAction.mockReset();
    createTemplateAction.mockResolvedValue({ ok: true, data: { id: "T1", name: "aviso", status: "PENDING", category: "UTILITY" } });
    mount();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "aviso pago_" } });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, recibimos tu pago." } });
    fireEvent.change(screen.getByLabelText("Ejemplo de nombre"), { target: { value: "Camila" } });
    fireEvent.click(screen.getByRole("button", { name: "Añadir botón" }));
    fireEvent.change(screen.getByLabelText("Texto del botón 1"), { target: { value: "Ver pedido" } });
    fireEvent.click(send());
    await waitFor(() => expect(createTemplateAction).toHaveBeenCalled());
    const sent = createTemplateAction.mock.calls[0]?.[0];
    expect(sent).toMatchObject({
      name: "aviso_pago",
      language: "es",
      category: "UTILITY",
      body_text: "Hola {{nombre}}, recibimos tu pago.",
      examples: { nombre: "Camila" },
      buttons: [{ type: "QUICK_REPLY", label: "Ver pedido" }],
    });
  });

  it("enseña el motivo de Meta dentro del diálogo cuando no la acepta", async () => {
    createTemplateAction.mockReset();
    createTemplateAction.mockResolvedValue({ ok: false, status: 400, message: "Meta rechazó la creación: nombre en uso." });
    mount();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "aviso" } });
    fireEvent.change(body(), { target: { value: "Gracias por tu compra." } });
    fireEvent.click(send());
    expect(await screen.findByText("No se pudo crear la plantilla")).toBeInTheDocument();
    expect(screen.getByText("Meta rechazó la creación: nombre en uso.")).toBeInTheDocument();
  });
});
