// @vitest-environment jsdom
/**
 * Requisitos 2.3, 2.4 y 2.6 — cambiar y archivar un teammate desde la app.
 *
 * Dos comportamientos que no se pueden equivocar:
 *
 * * **Guardar manda solo lo que cambió.** Un `PATCH` con todos los campos
 *   pisaría lo que otra persona del partner cambió entre que se abrió esta
 *   pantalla y se pulsó guardar — el roster es compartido.
 * * **Archivar no es borrar** y la pantalla tiene que decirlo antes, no
 *   después: los hilos siguen legibles y no hay vuelta atrás desde aquí.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import type { Teammate } from "../src/app/bridge";
import { LangProvider } from "../src/app/i18n";
import { TeammateSettings, type TeammateSettingsProps } from "../src/app/routes/teammate-settings";

afterEach(cleanup);

const MODELS = [
  { id: "openai/gpt-5.6-sol", note: "Sol", cost_label: "bajo" as const },
  { id: "openai/gpt-5.6-terra", note: "Terra", cost_label: "alto" as const },
];

const NILO: Teammate = {
  id: "11111111-2222-4333-8444-555555555555",
  name: "Nilo",
  job: "Desarrollo",
  model: "openai/gpt-5.6-sol",
  tool_names: ["console.whoami"],
  permissions: { read: true, write: false, spend: false, publish: false, contact: false },
  local_exec: false,
  status: "active",
  my_state: "en_espera",
  my_unread: false,
  my_thread_id: null,
  last_done: null,
};

function paint(props: Partial<TeammateSettingsProps> = {}) {
  const onSave = vi.fn().mockResolvedValue({ ok: true });
  const onArchive = vi.fn().mockResolvedValue({ ok: true });
  const onClose = vi.fn();
  render(
    <LangProvider value="es">
      <TeammateSettings
        teammate={NILO}
        jobs={["Desarrollo", "Finanzas"]}
        models={MODELS}
        onSave={onSave}
        onArchive={onArchive}
        onClose={onClose}
        {...props}
      />
    </LangProvider>,
  );
  return { onSave, onArchive, onClose };
}

const save = () => screen.getByRole("button", { name: /guardar/i });

describe("cambiar un teammate", () => {
  it("abre con lo que hay hoy y sin nada que guardar", () => {
    paint();
    expect(screen.getByLabelText(/nombre/i)).toHaveValue("Nilo");
    expect(screen.getByLabelText(/oficio/i)).toHaveValue("Desarrollo");
    expect(screen.getByRole("radio", { name: /Sol/i })).toBeChecked();
    expect(save()).toBeDisabled();
  });

  it("manda solo lo que cambió", async () => {
    const user = userEvent.setup();
    const { onSave } = paint();
    await user.clear(screen.getByLabelText(/oficio/i));
    await user.type(screen.getByLabelText(/oficio/i), "Finanzas");
    await user.click(save());

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({ job: "Finanzas" });
  });

  it("cambiar un permiso viaja como el juego completo de interruptores", async () => {
    // Los cinco van juntos porque la API los traduce a un catálogo entero:
    // mandar uno suelto dejaría el resto a interpretación del servidor.
    const user = userEvent.setup();
    const { onSave } = paint();
    await user.click(screen.getByRole("switch", { name: /publicar/i }));
    await user.click(save());

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({
      permissions: { read: true, write: false, spend: false, publish: true, contact: false },
    });
  });

  it("si el guardado falla, lo dice y no finge que se guardó", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue({ ok: false, error: "model_not_allowed" });
    paint({ onSave });
    await user.click(screen.getByRole("radio", { name: /Terra/i }));
    await user.click(save());

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent(/no está en la lista/i);
    expect(screen.getByRole("radio", { name: /Terra/i })).toBeChecked();
    expect(save()).not.toBeDisabled();
  });
});

describe("archivar un teammate", () => {
  it("pide confirmación y explica que no se borra", async () => {
    const user = userEvent.setup();
    const { onArchive } = paint();

    await user.click(screen.getByRole("button", { name: /^archivar/i }));

    expect(onArchive).not.toHaveBeenCalled();
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent(/no se borra/i);
    expect(dialog).toHaveTextContent(/hilos/i);
  });

  it("solo archiva cuando se confirma", async () => {
    const user = userEvent.setup();
    const { onArchive, onClose } = paint();
    await user.click(screen.getByRole("button", { name: /^archivar/i }));
    await user.click(screen.getByRole("button", { name: /sí, archivar/i }));

    await waitFor(() => expect(onArchive).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("se puede echar atrás sin archivar nada", async () => {
    const user = userEvent.setup();
    const { onArchive } = paint();
    await user.click(screen.getByRole("button", { name: /^archivar/i }));
    await user.click(screen.getByRole("button", { name: /mejor no/i }));

    expect(onArchive).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("un teammate archivado no se cambia: se lee", () => {
    paint({ teammate: { ...NILO, status: "archived" } });
    expect(screen.getByRole("status")).toHaveTextContent(/archivado/i);
    expect(screen.queryByRole("button", { name: /guardar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^archivar/i })).not.toBeInTheDocument();
  });
});
