import { act, fireEvent, render, screen } from "@testing-library/react-native";
import * as Reanimated from "react-native-reanimated";

import { MAX, durations } from "@/motion/durations";
import { motionFor } from "@/motion/use-motion";
import { EmptyState, ErrorState, OfflineBanner, PartialNotice, ReconnectingIndicator, SKELETON_DELAY_MS, Skeleton } from "@/ui/states";
import { Avatar } from "@/ui/bits";
import { Text } from "@/ui/text";

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
    jest.spyOn(Reanimated, "useReducedMotion").mockReturnValue(true);
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
