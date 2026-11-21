import { render, screen } from "@testing-library/react-native";
import { readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";
import { StyleSheet } from "react-native";

import { t as translate, type T } from "@/i18n/t";
import { slopFor } from "@/theme/theme";
import { tokens } from "@/theme/tokens.gen";

import { servicesConfig, TODAY } from "../test/reservas-fixtures";

const { Chip } = require("@/ui/chip") as typeof import("@/ui/chip");
const { Segmented } = require("@/ui/bits") as typeof import("@/ui/bits");
const { Field } = require("@/ui/field") as typeof import("@/ui/field");
const { Button } = require("@/ui/button") as typeof import("@/ui/button");
const { DayHeader } = require("@/features/reservas/header") as typeof import("@/features/reservas/header");
const { WEEK_LEVELS } = require("@/features/reservas/week") as typeof import("@/features/reservas/week");
const { Latest } = require("@/features/home/latest") as typeof import("@/features/home/latest");
const { stripWeekday } = require("@/features/reservas/format") as typeof import("@/features/reservas/format");

/**
 * Spec 069, the quality review (`revision.md`): what failed WCAG 2.2 AA and
 * Requisito 3.5, each one red first. SC-004 asks for none.
 */
const t: T = (k, v) => translate("es", k, v);
const noop = () => undefined;
const SCHEMES = ["light", "dark"] as const;

// ── contrast, from the generated tokens (alpha over its ground) ───────────

const channels = (hex: string) => {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).concat(h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1);
};
const over = (fg: string, ground: number[]) => {
  const [r, g, b, a] = channels(fg) as [number, number, number, number];
  const [R, G, B] = ground as [number, number, number];
  return [r * a + R * (1 - a), g * a + G * (1 - a), b * a + B * (1 - a)];
};
const luminance = ([r, g, b]: number[]) =>
  [r!, g!, b!].map((c) => (c / 255 <= 0.03928 ? c / 255 / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4)).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i]!, 0);
const ratio = (a: number[], b: number[]) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
};
function grounds(scheme: (typeof SCHEMES)[number]) {
  const c = tokens[scheme] as Record<string, string>;
  const background = over(c.background!, [0, 0, 0]);
  return { c, background, card: over(c.card!, background), muted: over(c.muted!, background) };
}
const on = (fg: string, ground: number[]) => ratio(over(fg, ground), ground);

describe("the tokens the fixes lean on", () => {
  it.each(SCHEMES)("control borders read at 3:1 on a card, the screen and a muted track (R3.5, H11, H08; %s)", (scheme) => {
    const { c, background, card, muted } = grounds(scheme);
    expect(c.controlBorder).toBeDefined();
    for (const ground of [card, background, muted]) expect(on(c.controlBorder!, ground)).toBeGreaterThanOrEqual(3.2);
  });

  it.each(SCHEMES)("a placeholder's ink reads at 4.5:1 on a card and on the screen (1.4.3, H09; %s)", (scheme) => {
    const { c, background, card } = grounds(scheme);
    for (const ground of [card, background]) expect(on(c.mutedForeground!, ground)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(SCHEMES)("the dots that mean something read at 3:1 (1.4.11, H06, H07; %s)", (scheme) => {
    const { c, background, card } = grounds(scheme);
    for (const ground of [card, background]) expect(on(c.highlightInk!, ground)).toBeGreaterThanOrEqual(3);
  });

  it.each(SCHEMES)("every step of Aforo's week reads its number at 4.5:1 on its cell (1.4.3, H04; %s)", (scheme) => {
    const { c, background } = grounds(scheme);
    for (const level of Object.values(WEEK_LEVELS)) {
      const cell = over(c[level.bg]!, background);
      expect({ level, contrast: on(c[level.fg]!, cell) >= 4.5 }).toEqual({ level, contrast: true });
    }
  });
});

describe("where they are used", () => {
  const light = tokens.light;

  it("a chip that isn't chosen has a 3:1 border (R3.5, H11)", async () => {
    await render(<Chip label="Instagram" on={false} onPress={noop} testID="chip" />);
    expect(StyleSheet.flatten(screen.getByTestId("chip").props.style).borderColor).toBe(light.controlBorder);
  });

  it("the chosen segment is told apart by a 3:1 border, not by a white card alone (1.4.11, H08)", async () => {
    await render(<Segmented options={[{ value: "day", label: "Día" }, { value: "week", label: "Semana" }]} value="day" onChange={noop} label="Periodo" />);
    const chosen = StyleSheet.flatten(screen.getByRole("radio", { name: "Día" }).props.style);
    expect(chosen.borderColor).toBe(light.controlBorder);
    expect(chosen.borderWidth).toBeGreaterThan(0);
  });

  it("list or grid: the chosen one has the same 3:1 border (1.4.11, H08)", async () => {
    await render(<DayHeader period="day" onPeriod={noop} date={TODAY} today={TODAY} onDate={noop} config={servicesConfig} view="list" onView={noop} t={t} locale="es" />);
    expect(StyleSheet.flatten(screen.getByRole("radio", { name: "Lista" }).props.style).borderColor).toBe(light.controlBorder);
  });

  it("a field's placeholder is in the muted ink, not the 3.6:1 one (1.4.3, H09)", async () => {
    await render(<Field label="Teléfono" value="" onChangeText={noop} placeholder="+56 9 1234 5678" />);
    expect(screen.getByLabelText("Teléfono").props.placeholderTextColor).toBe(light.mutedForeground);
  });

  it("no placeholder anywhere in the app is in the subtle ink (1.4.3, H09)", () => {
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.tsx?$/.test(name)) files.push(path);
      }
    };
    walk(join(__dirname, "..", "src"));
    const offenders = files.filter((f) => /placeholderTextColor=\{[^}]*subtle/.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });

  it("the strip's dots are in the readable mint and the day says it has bookings (1.4.11, 1.3.1, H07)", async () => {
    await render(
      <DayHeader period="day" onPeriod={noop} date={TODAY} today={TODAY} onDate={noop} config={servicesConfig} view="list" onView={noop} marks={new Set(["2026-10-20", TODAY])} t={t} locale="es" />,
    );
    expect(StyleSheet.flatten(screen.getByTestId("strip-dot-2026-10-20").props.style).backgroundColor).toBe(light.highlightInk);
    expect(screen.getByLabelText("Martes, 20 de octubre, con reservas")).toBeTruthy();
    expect(screen.getByLabelText("Jueves, 22 de octubre, hoy, con reservas")).toBeTruthy();
    expect(screen.getByLabelText("Miércoles, 21 de octubre")).toBeTruthy();
  });

  it("Inicio's unread dot is in the readable mint (1.4.11, H06)", async () => {
    const c = {
      id: "c1",
      contact: { name: "Nuria Campos", handle: "@nuria", initials: "NC", has_avatar: false },
      channel: { kind: "instagram" },
      agent: { id: "a1", name: "Ava" },
      handled_by_agent: { id: "a1", name: "Ava" },
      state: "agent",
      assignee: null,
      last_message: { at: new Date().toISOString(), author: { kind: "agent", name: "Ava", is_me: false }, preview: "Hola", has_media: false },
      unread: true,
      tags: [],
    };
    await render(<Latest peek={{ state: "ready", items: [c] } as never} someoneWaits={false} agents={[{ name: "Ava" }]} t={t} onOpen={noop} />);
    const halo = screen.getByTestId("home-latest-unread");
    const dot = (halo.props.children as { props: { style: unknown } }).props.style;
    expect(StyleSheet.flatten(dot as never).backgroundColor).toBe(light.highlightInk);
  });
});

describe("the strip's «today» in the case of its neighbours (review H17)", () => {
  const en: T = (k, v) => translate("en", k, v);
  it("Spanish writes its days in lower case, so «hoy»", () => {
    expect(stripWeekday(TODAY, true, t, "es")).toBe("hoy");
    expect(stripWeekday("2026-10-19", false, t, "es")).toBe("lun");
  });
  it("English capitalises them, so «Today» beside «Mon»", () => {
    expect(stripWeekday(TODAY, true, en, "en")).toBe("Today");
    expect(stripWeekday("2026-10-19", false, en, "en")).toBe("Mon");
  });
});

describe("small targets reach the platform's minimum (R3.3, review H21)", () => {
  it("a 32-tall half hour reaches 44 pt on iOS and 48 dp on Android", () => {
    expect(slopFor(32, 44)).toEqual({ top: 6, bottom: 6 });
    expect(slopFor(32, 48)).toEqual({ top: 8, bottom: 8 });
  });
  it("a target already big enough gets none", () => {
    expect(slopFor(60, 48)).toEqual({ top: 0, bottom: 0 });
  });
  it("the half hour free, a short block and «Corregir» use it, not a fixed 6", async () => {
    const files = ["features/reservas/day-grid.tsx", "features/inbox/thread/bubble.tsx"].map((f) => readFileSync(join(__dirname, "..", "src", f), "utf8"));
    for (const f of files) expect(f).not.toMatch(/hitSlop=\{\{ top: 6, bottom: 6/);
  });
});

describe("found in the iOS simulator (T052)", () => {
  /** The row that holds a button's icon and words: the nearest ancestor laid out in a row. */
  type Node = { props: { style?: unknown }; parent: Node | null };
  const styleOf = (n: Node | null) => (n ? ((StyleSheet.flatten(n.props.style as never) ?? {}) as { flexDirection?: string; flexWrap?: string }) : {});
  const rowOf = (label: string) => {
    let n = screen.getByText(label) as unknown as Node | null;
    while (n && styleOf(n).flexDirection !== "row") n = n.parent;
    return styleOf(n);
  };
  it("a compact button keeps its icon and words on one line beside a growing text («Devolver» in the foot)", async () => {
    await render(<Button label="Devolver" icon={{ lucide: () => null, ios: "arrow.uturn.left", android: "undo" } as never} variant="secondary" compact onPress={noop} />);
    expect(rowOf("Devolver").flexWrap).toBe("nowrap");
  });
  it("a button beside another («Pedir confirmación») wraps its words beside the icon, never under it", async () => {
    await render(<Button label="Pedir confirmación" icon={{ lucide: () => null, ios: "bell", android: "notifications" } as never} variant="secondary" onPress={noop} />);
    expect(rowOf("Pedir confirmación").flexWrap).toBe("nowrap");
    expect(StyleSheet.flatten(screen.getByText("Pedir confirmación").props.style).flexShrink).toBe(1);
  });
});
