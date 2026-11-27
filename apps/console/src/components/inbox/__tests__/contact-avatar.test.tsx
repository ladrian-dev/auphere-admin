import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { parseColor, ratioOn, type Color } from "@nexus/ui/lib/contrast";
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { AVATAR_TONES, ContactAvatar, contactTone } from "../contact-avatar";
import { Thread } from "../thread";
import { message } from "./fixtures";

/**
 * Owner, 2026-10-30: the inbox shows the person's photo (Instagram /
 * Messenger). It comes from our BFF route, never a storage link; without one,
 * or if it fails to load, the initials.
 */
describe("ContactAvatar", () => {
  const ID = "11111111-1111-4111-8111-111111111111";

  it("shows the picture from the BFF route when there is one", () => {
    const { container } = render(<ContactAvatar conversationId={ID} hasAvatar initials="AN" className="size-10" />);
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe(`/api/lite/inbox/avatar/${ID}`);
    expect(img?.getAttribute("alt")).toBe("");
  });

  it("falls back to the initials without a picture or when it fails", () => {
    const none = render(<ContactAvatar conversationId={ID} initials="AN" className="size-10" />);
    expect(none.container.querySelector("img")).toBeNull();
    expect(none.container.textContent).toBe("AN");
    none.unmount();

    const broken = render(<ContactAvatar conversationId={ID} hasAvatar initials="AN" className="size-10" />);
    fireEvent.error(broken.container.querySelector("img")!);
    expect(broken.container.querySelector("img")).toBeNull();
    expect(broken.container.textContent).toBe("AN");
  });
});

/**
 * Spec 082, Historia 5: cada contacto se reconoce. WhatsApp no da foto, así que
 * el color es lo que distingue a dos contactos de un vistazo.
 */
describe("ContactAvatar — un color por contacto (5.1)", () => {
  const ids = Array.from({ length: 60 }, (_, i) => `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`);

  /** El tono que pinta un avatar: la clase de la tabla que lleva su círculo. */
  function toneOf(el: Element | null): number {
    const cls = el?.getAttribute("class") ?? "";
    return AVATAR_TONES.findIndex((t) => t.className.split(" ").every((c) => cls.split(/\s+/).includes(c)));
  }

  it("el mismo id da el mismo color, en la lista, la conversación y el panel", () => {
    const id = ids[7]!;
    // Los tres tamaños de las tres vistas (fila, cabecera, panel).
    const row = render(<ContactAvatar conversationId={id} initials="AN" className="size-10 text-sm" />);
    const header = render(<ContactAvatar conversationId={id} initials="AN" className="size-10 text-sm" />);
    const panel = render(<ContactAvatar conversationId={id} initials="AN" className="size-12 text-base" />);
    const tone = toneOf(row.container.firstElementChild);
    expect(tone).toBeGreaterThanOrEqual(0);
    expect(toneOf(header.container.firstElementChild)).toBe(tone);
    expect(toneOf(panel.container.firstElementChild)).toBe(tone);
    expect(contactTone(id)).toBe(tone);
    expect(contactTone(id)).toBe(contactTone(id));
  });

  it("los contactos se reparten entre los seis tonos", () => {
    const used = new Set(ids.map(contactTone));
    expect(used.size).toBe(AVATAR_TONES.length);
    expect(AVATAR_TONES).toHaveLength(6);
  });

  it("en la conversación, el círculo de cada mensaje del contacto lleva su mismo tono", () => {
    const id = ids[11]!;
    const { container } = render(
      <LocaleProvider locale="es">
        <Thread items={[message(), message()]} hasOlder={false} loadingOlder={false} contactId={id} contactInitials="·" now={new Date("2026-10-08T12:00:00Z")} onOlder={() => {}} />
      </LocaleProvider>,
    );
    const circles = [...container.querySelectorAll("span[aria-hidden='true'].rounded-full")];
    expect(circles).toHaveLength(2);
    for (const c of circles) {
      expect(toneOf(c)).toBe(contactTone(id));
      expect(c.querySelector("svg")).not.toBeNull();
      expect(c.textContent).toBe("");
    }
    expect(container.textContent).not.toContain("·");
  });

  it("sin letras (solo un número), un icono de persona y nunca «·» (5.3)", () => {
    for (const initials of ["·", ""]) {
      const { container, unmount } = render(<ContactAvatar conversationId={ids[3]!} initials={initials} className="size-10" />);
      expect(container.querySelector("svg")).not.toBeNull();
      expect(container.textContent).toBe("");
      expect(toneOf(container.firstElementChild)).toBe(contactTone(ids[3]!));
      unmount();
    }
  });
});

/**
 * 5.2: cada par de fondo y texto pasa AA (4,5:1) en los dos temas, sale de los
 * tokens de `@nexus/ui` y no usa ámbar ni rojo. Se mide sobre `tokens.css`,
 * como la prueba de contraste del propio design system.
 */
describe("ContactAvatar — los seis tonos pasan AA en claro y oscuro (5.2)", () => {
  const TOKENS = readFileSync(createRequire(import.meta.url).resolve("@nexus/ui/tokens.css"), "utf8");

  function block(selector: RegExp): Map<string, string> {
    const start = TOKENS.search(selector);
    if (start < 0) throw new Error(`no encuentro el bloque ${selector}`);
    const open = TOKENS.indexOf("{", start);
    const close = TOKENS.indexOf("\n}", open);
    const out = new Map<string, string>();
    for (const m of TOKENS.slice(open, close).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out.set(m[1]!, m[2]!.trim());
    return out;
  }
  const theme = block(/@theme\s*\{/);
  const scopes = { claro: block(/^:root \{/m), oscuro: block(/^\[data-theme="dark"\] \{/m) };

  /** El nombre de Tailwind (`pine`, `secondary`) es `--color-pine` o el puente `--secondary`. */
  function raw(name: string, scope: Map<string, string>): string {
    const first = [`--color-${name}`, `--${name}`].find((v) => scope.has(v) || theme.has(v));
    if (!first) throw new Error(`«${name}» no es un token de @nexus/ui`);
    let value = scope.get(first) ?? theme.get(first);
    const seen = new Set<string>();
    while (value?.startsWith("var(")) {
      const next = value.match(/var\((--[\w-]+)/)?.[1];
      if (!next || seen.has(next)) break;
      seen.add(next);
      value = scope.get(next) ?? theme.get(next);
    }
    if (!value) throw new Error(`no puedo resolver ${name}`);
    return value.replace(/\s*\/\*.*?\*\/\s*/g, "").trim();
  }
  function color(name: string, scope: Map<string, string>): Color {
    const c = parseColor(raw(name, scope));
    if (!c) throw new Error(`${name} no es un color medible`);
    return c;
  }
  /** Ámbar y rojo: el tono OKLCH de 0 a 100 con algo de croma. */
  function warm(name: string, scope: Map<string, string>): boolean {
    const m = raw(name, scope).match(/^oklch\(\s*[\d.]+%?\s+([\d.]+)\s+([\d.]+)/);
    return Boolean(m && Number(m[1]) > 0.02 && Number(m[2]) <= 100);
  }

  const cases = AVATAR_TONES.flatMap((t, i) =>
    (Object.keys(scopes) as (keyof typeof scopes)[]).map((tema) => ({ i, tema, bg: t[tema === "claro" ? "light" : "dark"][0], fg: t[tema === "claro" ? "light" : "dark"][1] })),
  );

  it.each(cases)("tono $i en $tema: $fg sobre $bg", ({ tema, bg, fg }) => {
    const scope = scopes[tema];
    expect(Number(ratioOn(color(fg, scope), color(bg, scope)).toFixed(2))).toBeGreaterThanOrEqual(4.5);
    for (const name of [bg, fg]) {
      expect(name).not.toMatch(/warning|danger|destructive|amber|red/);
      expect(warm(name, scope)).toBe(false);
    }
  });

  it("la clase de cada tono es la de sus tokens, también en oscuro", () => {
    for (const t of AVATAR_TONES) {
      const [bg, fg] = t.light;
      const [dbg, dfg] = t.dark;
      const expected = [`bg-${bg}`, `text-${fg}`, ...(dbg !== bg ? [`dark:bg-${dbg}`] : []), ...(dfg !== fg ? [`dark:text-${dfg}`] : [])];
      expect(t.className).toBe(expected.join(" "));
    }
  });
});
