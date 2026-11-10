import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { StyleSheet } from "react-native";
import * as Reanimated from "react-native-reanimated";

import { MAX, durations } from "@/motion/durations";
import { motionFor } from "@/motion/use-motion";
import { CARD_RADIUS, concentric } from "@/theme/theme";
import { EmptyState, ErrorState, OfflineBanner, PartialNotice, ReconnectingIndicator, SKELETON_DELAY_MS, Skeleton } from "@/ui/states";
import { Avatar } from "@/ui/bits";
import { Text } from "@/ui/text";

const noop = () => undefined;

/**
 * Spec 031 (T014, T029, R14.1, R14.2, R14.4, R14.7): the five states, named
 * for assistive tech, and the motion budget.
 */
describe("the five states", () => {
  it("the skeleton is announced at once but only drawn past 300 ms", async () => {
    jest.useFakeTimers();
    await render(<Skeleton rows={2} />);
    expect(screen.getByRole("progressbar", { name: "Cargando" })).toBeTruthy();
    expect(screen.queryAllByTestId("skeleton-row")).toHaveLength(0);
    await act(async () => {
      jest.advanceTimersByTime(SKELETON_DELAY_MS);
    });
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(2);
    jest.useRealTimers();
  });

  it("empty says what and offers the way out", async () => {
    const onPress = jest.fn();
    await render(<EmptyState title="Aún no hay conversaciones" body="Cuando alguien escriba…" action={{ label: "Ver todas", onPress }} />);
    expect(screen.getByRole("header", { name: "Aún no hay conversaciones" })).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Ver todas" }));
    expect(onPress).toHaveBeenCalled();
  });

  it("error is an alert with a retry", async () => {
    const onRetry = jest.fn();
    await render(<ErrorState onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("puts «Reintentar» under the words, centred like them (spec 044, first iOS pass: it sat on the left)", async () => {
    await render(<ErrorState onRetry={noop} />);
    expect(StyleSheet.flatten(screen.getByTestId("error-retry").props.style)).toMatchObject({ alignSelf: "center" });
  });

  it("offline says that what shows is the last thing that loaded, and since when", async () => {
    await render(<OfflineBanner since="10:42" />);
    expect(screen.getByText("Sin conexión. Ves lo último que se cargó.")).toBeTruthy();
    expect(screen.getByText("Sin actualizar desde las 10:42")).toBeTruthy();
  });

  it("partial is said once, as an alert", async () => {
    await render(<PartialNotice />);
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("«Reconectando…» is named, and still with reduced motion", async () => {
    const repeat = jest.spyOn(Reanimated, "withRepeat");
    const appearance = require("@/theme/system-appearance") as { useSystemAppearance: () => unknown };
    jest.spyOn(appearance, "useSystemAppearance").mockReturnValue({ reduceTransparency: false, increaseContrast: false, reduceMotion: true });
    await render(<ReconnectingIndicator label="Reconectando…" />);
    expect(screen.getByLabelText("Reconectando…")).toBeTruthy();
    expect(repeat).not.toHaveBeenCalled();
    jest.restoreAllMocks();
  });

  it("text never opts out of the system's text size, nor is cut by default (R14.4)", async () => {
    await render(<Text>Una frase larga que tiene que poder crecer con el tamaño del sistema</Text>);
    const node = screen.getByText(/Una frase larga/);
    expect(node.props.allowFontScaling).not.toBe(false);
    expect(node.props.numberOfLines).toBeUndefined();
  });
});

describe("motion (D24)", () => {
  it("every duration is inside the 300 ms budget", () => {
    for (const ms of Object.values(durations)) expect(ms).toBeLessThanOrEqual(MAX);
  });

  it("with reduced motion, entrances are fades and nothing slides or morphs", () => {
    const reduced = motionFor(true);
    const full = motionFor(false);
    expect(reduced.enter).toBe(reduced.fade);
    expect(reduced.layout).toBeUndefined();
    expect(full.enter).not.toBe(full.fade);
    expect(full.layout).toBeDefined();
  });

  it("tells Reanimated explicitly, never «System» — the app decides what reduced motion looks like (spec 042, T022, R2.6, R4.5)", () => {
    const motion = (b: unknown) => (b as { motion?: unknown }).motion;
    const reduced = motionFor(true);
    const full = motionFor(false);
    // The fade IS the reduced-motion alternative, so it must play: «Always» would skip it.
    expect(motion(reduced.enter)).toBe(Reanimated.ReduceMotion.Never);
    expect(motion(reduced.exit)).toBe(Reanimated.ReduceMotion.Never);
    expect(motion(full.enter)).toBe(Reanimated.ReduceMotion.Never);
    expect(motion(full.layout)).toBe(Reanimated.ReduceMotion.Never);
    expect((full.layout as unknown as { ms?: number }).ms).toBe(durations.state);
  });

  it("useMotion follows the phone's setting live, not the value at launch (T022)", async () => {
    const appearance = require("@/theme/system-appearance") as { useSystemAppearance: () => unknown };
    jest.spyOn(appearance, "useSystemAppearance").mockReturnValue({ reduceTransparency: false, increaseContrast: false, reduceMotion: true });
    const { useMotion } = require("@/motion/use-motion") as { useMotion: () => { reduced: boolean } };
    const { renderHook } = require("@testing-library/react-native") as typeof import("@testing-library/react-native");
    expect((await renderHook(() => useMotion())).result.current.reduced).toBe(true);
    jest.restoreAllMocks();
  });
});

describe("shape (spec 042, T006, R7.1)", () => {
  it("cards share one radius, and what sits inside keeps its corners concentric", () => {
    expect(CARD_RADIUS).toBe(12);
    expect(concentric(24, 8)).toBe(16);
    expect(concentric(12, 12)).toBe(4);
    expect(concentric(6, 10)).toBe(4);
  });
});

describe("buttons, in the platform's shape and touch (spec 042, T071, T078, R4.8, R7.1, R7.2, R10.4)", () => {
  const { Platform, StyleSheet } = require("react-native") as typeof import("react-native");
  const { tokens } = require("@/theme/tokens.gen") as typeof import("@/theme/tokens.gen");
  const { TOUCH } = require("@/theme/theme") as typeof import("@/theme/theme");
  const { Button, IconButton } = require("@/ui/button") as typeof import("@/ui/button");
  const style = (name: string) => StyleSheet.flatten(screen.getByRole("button", { name }).props.style) as Record<string, unknown>;

  it("is a capsule with the full touch target, and pressing tints it — the opacity never moves", async () => {
    await render(<Button label="Tomar el control" onPress={() => undefined} />);
    expect(style("Tomar el control").borderRadius).toBe(tokens.radius.full);
    expect(style("Tomar el control").minHeight).toBe(TOUCH);
    expect(style("Tomar el control").minWidth).toBe(TOUCH);
    expect(style("Tomar el control").backgroundColor).toBe(tokens.light.primary);
    await fireEvent(screen.getByRole("button", { name: "Tomar el control" }), "pressIn");
    expect(style("Tomar el control").backgroundColor).toBe(tokens.light.primaryDeep);
    expect(style("Tomar el control").opacity).toBeUndefined();
    await fireEvent(screen.getByRole("button", { name: "Tomar el control" }), "pressOut");
    expect(style("Tomar el control").backgroundColor).toBe(tokens.light.primary);
  });

  it("a secondary one presses to the muted tone", async () => {
    await render(<Button label="Reabrir" variant="secondary" onPress={() => undefined} />);
    expect(style("Reabrir").backgroundColor).toBe(tokens.light.card);
    await fireEvent(screen.getByRole("button", { name: "Reabrir" }), "pressIn");
    expect(style("Reabrir").backgroundColor).toBe(tokens.light.muted);
  });

  it("on iOS the press is a scale to 0.97 inside the fast budget; on Android it is the ripple", async () => {
    const timing = jest.spyOn(Reanimated, "withTiming");
    await render(<Button label="Enviar" onPress={() => undefined} />);
    await fireEvent(screen.getByRole("button", { name: "Enviar" }), "pressIn");
    expect(timing).toHaveBeenCalledWith(0.97, expect.objectContaining({ duration: durations.fast }));
    await fireEvent(screen.getByRole("button", { name: "Enviar" }), "pressOut");
    expect(timing).toHaveBeenLastCalledWith(1, expect.objectContaining({ duration: durations.fast }));
    // Pressable turns `android_ripple` into the host's native background, only on Android.
    expect(screen.getByRole("button", { name: "Enviar" }).props.nativeBackgroundAndroid).toBeUndefined();
    timing.mockRestore();

    const os = jest.replaceProperty(Platform, "OS", "android");
    await render(<Button label="Guardar" onPress={() => undefined} />);
    expect(screen.getByRole("button", { name: "Guardar" }).props.nativeBackgroundAndroid).toEqual(expect.objectContaining({ type: "RippleAndroid" }));
    os.restore();
  });

  it("disabled lowers the contrast of the content, not the opacity of the button; busy keeps the size (R4.8)", async () => {
    await render(<Button label="Devolver" disabled onPress={() => undefined} />);
    expect(style("Devolver").opacity).toBeUndefined();
    expect(StyleSheet.flatten(screen.getByText("Devolver").props.style).color).toBe(tokens.light.mutedForeground);
    expect(screen.getByRole("button", { name: "Devolver" }).props.accessibilityState.disabled).toBe(true);

    await render(<Button label="Guardando" busy onPress={() => undefined} />);
    expect(style("Guardando").minHeight).toBe(TOUCH);
    expect(style("Guardando").opacity).toBeUndefined();
    expect(screen.getByRole("button", { name: "Guardando" }).props.accessibilityState.busy).toBe(true);
  });

  it("the icon button presses to a tint too, never to a lower opacity", async () => {
    await render(<IconButton icon={{ ios: "ellipsis.circle", android: "more_vert" }} label="Más" onPress={() => undefined} />);
    await fireEvent(screen.getByRole("button", { name: "Más" }), "pressIn");
    expect(style("Más").opacity).toBeUndefined();
    expect(style("Más").backgroundColor).toBe(tokens.light.muted);
    expect(style("Más").borderRadius).toBe(tokens.radius.full);
  });
});

describe("type, in the system's own styles on iOS and the tokens on Android (spec 042, T079, R7.3, R7.4)", () => {
  const load = (os: "ios" | "android") => {
    let t: typeof import("@/theme/type").type | undefined;
    jest.isolateModules(() => {
      const { Platform } = require("react-native") as typeof import("react-native");
      const restore = jest.replaceProperty(Platform, "OS", os);
      t = (require("@/theme/type") as typeof import("@/theme/type")).type;
      restore.restore();
    });
    return t!;
  };

  it("iOS: body 17/22, headline 17 semibold, title 22, largeTitle 34, figure 28 tabular — and no letterSpacing anywhere", () => {
    const t = load("ios");
    expect([t.body.fontSize, t.body.lineHeight, t.body.fontWeight]).toEqual([17, 22, "400"]);
    expect([t.bodyStrong.fontSize, t.bodyStrong.fontWeight]).toEqual([17, "600"]);
    expect([t.headline.fontSize, t.headline.lineHeight, t.headline.fontWeight]).toEqual([17, 22, "600"]);
    expect([t.title.fontSize, t.title.lineHeight]).toEqual([22, 28]);
    expect([t.largeTitle.fontSize, t.largeTitle.lineHeight]).toEqual([34, 41]);
    expect([t.figure.fontSize, t.figure.lineHeight, t.figure.fontVariant]).toEqual([28, 34, ["tabular-nums"]]);
    expect([t.callout.fontSize, t.subhead.fontSize, t.footnote.fontSize, t.caption.fontSize]).toEqual([16, 15, 13, 12]);
    for (const v of Object.values(t)) expect((v as { letterSpacing?: number }).letterSpacing).toBeUndefined();
  });

  it("the native bars' titles follow Apple's Dynamic Type table and never fall under the body (R4.6, H8)", () => {
    const { headerSize } = require("@/theme/type") as typeof import("@/theme/type");
    expect(headerSize("largeTitle", 1)).toBe(34);
    expect(headerSize("largeTitle", 1.65)).toBe(44);
    expect(headerSize("largeTitle", 3.12)).toBe(60);
    expect(headerSize("largeTitle", 4)).toBe(60);
    expect(headerSize("largeTitle", 0.5)).toBe(31);
    // The body scales linearly with the phone's factor; the large title must stay above it.
    for (const f of [1, 1.35, 1.65, 2.35, 3.12]) expect(headerSize("largeTitle", f)).toBeGreaterThan(17 * f * 0.99);
  });

  it("on iOS every style stops where Apple's table stops, and the large title stays above the title at the largest size (R4.6)", async () => {
    const { maxScale } = require("@/theme/type") as typeof import("@/theme/type");
    const { Text } = require("@/ui/text") as typeof import("@/ui/text");
    expect(maxScale.largeTitle).toBeCloseTo(60 / 34, 3);
    expect(maxScale.title).toBeCloseTo(43 / 22, 3);
    expect(maxScale.body).toBeCloseTo(53 / 17, 3);
    expect(34 * maxScale.largeTitle).toBeGreaterThan(22 * maxScale.title);
    await render(<Text variant="title">Flor y Encanto</Text>);
    expect(screen.getByText("Flor y Encanto").props.maxFontSizeMultiplier).toBeCloseTo(43 / 22, 3);
  });

  it("Android: the tokens' scale", () => {
    const { tokens } = require("@/theme/tokens.gen") as typeof import("@/theme/tokens.gen");
    const t = load("android");
    expect(t.body.fontSize).toBe(tokens.text.base);
    expect(t.largeTitle.fontSize).toBe(tokens.text["2xl"]);
    expect(t.title.fontSize).toBe(tokens.text.xl);
    expect(t.headline.fontSize).toBe(tokens.text.md);
    expect(t.caption.fontSize).toBe(tokens.text.xs);
    for (const v of Object.values(t)) expect((v as { letterSpacing?: number }).letterSpacing).toBeUndefined();
  });
});

describe("the avatar", () => {
  it("draws the initials, and a person — not a dot — for a contact known only by number", async () => {
    await render(<Avatar initials="AL" />);
    expect(screen.getByText("AL", { includeHiddenElements: true })).toBeTruthy();
    await render(<Avatar initials="·" />);
    expect(screen.queryByText("·", { includeHiddenElements: true })).toBeNull();
    expect(screen.getByTestId("avatar-person", { includeHiddenElements: true })).toBeTruthy();
  });
});
