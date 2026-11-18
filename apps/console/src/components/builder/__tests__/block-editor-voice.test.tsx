import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AgentSpec } from "@/lib/backend/builder-types";

import { BlockEditor } from "../block-editor";

/**
 * «Cómo habla» (el owner, 2026-10-28): el tono se elige de una lista y los
 * idiomas se marcan por su nombre, no se escriben como códigos. El AgentSpec
 * no cambia: `voice.tone` sigue siendo texto y `voice.languages` los mismos
 * códigos, el principal primero.
 */

const SPEC: AgentSpec = {
  schema_version: "1",
  mode: "structured",
  identity: { name: "Recepción", description: "Atiende las citas por WhatsApp y responde precios." },
  voice: { tone: "Cercano", languages: ["es"], register: "tu" },
  ai_disclosure: { decided: false },
};

function editor(voice: AgentSpec["voice"] = SPEC.voice) {
  const onSave = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <BlockEditor block="voice" spec={{ ...SPEC, voice }} busy={false} label="Editar «Cómo habla»" onSave={onSave} onCancel={vi.fn()} />
    </LocaleProvider>,
  );
  return { ...view, onSave };
}

const languages = () => screen.getByRole("group", { name: "Idiomas" });

describe("«Cómo habla» · el tono", () => {
  it("es una lista con tonos de siempre y el actual elegido", () => {
    editor();
    const tone = screen.getByRole("combobox", { name: /Tono/ });
    expect(tone).toHaveValue("Cercano");
    expect(within(tone).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Sin indicar",
      "Cercano",
      "Amable",
      "Profesional",
      "Formal",
      "Directo",
      "Divertido",
    ]);
  });

  it("un tono escrito antes a mano sigue en la lista, elegido", () => {
    editor({ tone: "Cercano y claro", languages: ["es"] });
    const tone = screen.getByRole("combobox", { name: /Tono/ });
    expect(tone).toHaveValue("Cercano y claro");
    expect(within(tone).getByRole("option", { name: "Cercano y claro" })).toBeInTheDocument();
  });
});

describe("«Cómo habla» · los idiomas", () => {
  it("se marcan por su nombre, sin escribir códigos, y dice cuál es el principal; pasa axe", async () => {
    const { container } = editor();
    expect(screen.queryByRole("textbox", { name: /Idiomas/ })).toBeNull();
    // Cada uno con su nombre en su idioma, en este orden.
    const names = ["Español", "English", "Português", "Français", "Italiano", "Deutsch", "Català"];
    // Los idiomas; la casilla de «Responder solo en estos idiomas» va aparte (spec 063).
    const boxes = within(languages())
      .getAllByRole("checkbox")
      .filter((box) => box.getAttribute("data-slot") !== "voice-language-limit");
    expect(boxes).toHaveLength(names.length);
    names.forEach((name, i) => expect(within(languages()).getByRole("checkbox", { name })).toBe(boxes[i]));
    expect(within(languages()).getByRole("checkbox", { name: "Español" })).toBeChecked();
    expect(screen.getByText("Contesta en el idioma del cliente. Si no lo sabe, en Español.")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("el primero que se marca es el principal y se guarda con los mismos códigos", async () => {
    const user = userEvent.setup();
    const { onSave } = editor();
    await user.click(within(languages()).getByRole("checkbox", { name: /English/ }));
    await user.click(within(languages()).getByRole("checkbox", { name: /Español/ }));
    expect(screen.getByText("Contesta en el idioma del cliente. Si no lo sabe, en English.")).toBeVisible();
    await user.click(within(languages()).getByRole("checkbox", { name: /Català/ }));
    await user.selectOptions(screen.getByRole("combobox", { name: /Tono/ }), "Formal");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(onSave).toHaveBeenCalledWith({ tone: "Formal", languages: ["en", "ca"], register: "tu" });
  });

  it("un código que no está en la lista sale con su nombre y se conserva", async () => {
    const user = userEvent.setup();
    const { onSave } = editor({ languages: ["pt-BR", "es"] });
    const extra = within(languages()).getByRole("checkbox", { name: /portugués de Brasil/i });
    expect(extra).toBeChecked();
    expect(screen.getByText(/Si no lo sabe, en portugués de Brasil\.$/i)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(onSave).toHaveBeenCalledWith({ languages: ["pt-BR", "es"] });
  });

  it("como mucho cinco: con cinco marcados, los demás no se pueden marcar", async () => {
    const user = userEvent.setup();
    editor({ languages: ["es", "en", "pt", "fr", "it"] });
    expect(within(languages()).getByRole("checkbox", { name: /Deutsch/ })).toBeDisabled();
    await user.click(within(languages()).getByRole("checkbox", { name: /Italiano/ }));
    expect(within(languages()).getByRole("checkbox", { name: /Deutsch/ })).toBeEnabled();
  });
});

/**
 * Spec 063 (requisitos 1.6 y 1.8): por defecto el agente contesta en el idioma del
 * cliente. «Responder solo en estos idiomas» lo limita a los marcados; si le
 * escriben en otro, contesta en el principal. Una línea dice qué hace.
 */
describe("«Cómo habla» · limitar los idiomas (spec 063)", () => {
  const limit = () => screen.getByRole("checkbox", { name: "Responder solo en estos idiomas" });

  it("empieza sin límite y no lo guarda", async () => {
    const user = userEvent.setup();
    const { onSave } = editor({ languages: ["es", "en"] });
    expect(limit()).not.toBeChecked();
    expect(screen.getByText("Contesta en el idioma del cliente. Si no lo sabe, en Español.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(onSave).toHaveBeenCalledWith({ languages: ["es", "en"] });
  });

  it("encendido, dice en cuáles y lo guarda; pasa axe", async () => {
    const user = userEvent.setup();
    const { onSave, container } = editor({ languages: ["es", "en"] });
    await user.click(limit());
    expect(screen.getByText("Solo en: Español, English. Si le escriben en otro, en Español.")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(onSave).toHaveBeenCalledWith({ languages: ["es", "en"], languages_limited: true });
  });

  it("un agente ya limitado sale con el límite puesto, y apagarlo lo quita", async () => {
    const user = userEvent.setup();
    const { onSave } = editor({ languages: ["es"], languages_limited: true });
    expect(limit()).toBeChecked();
    await user.click(limit());
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(onSave).toHaveBeenCalledWith({ languages: ["es"] });
  });
});

