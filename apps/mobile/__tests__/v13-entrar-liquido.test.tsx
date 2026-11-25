import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { AccessibilityInfo, AppState, Text } from "react-native";

import { WARMUP_FRAMES } from "@/features/entry/liquid-pace";
import { STILL_T } from "@/features/entry/liquid.gen";

/**
 * Spec 069 (R5.2, R5.3, R22.4, D8): the live liquid on the UI thread — the
 * finger, the waves, the still frame and when it stops. Skia, the gesture
 * handler and the frame callback are doubles here; what they are fed is real.
 */
type Uniforms = { R: number[]; T: number; P: number[]; W: number[] };
type FrameInfo = { timestamp: number; timeSincePreviousFrame: number | null; timeSinceFirstFrame: number };
type Touches = { changedTouches: { x: number; y: number }[] };

const mockFrame = { callback: null as null | ((i: FrameInfo) => void), setActive: jest.fn() };
const mockGesture = { config: null as null | { enabled?: boolean; onTouchesDown?: (e: Touches) => void; onTouchesMove?: (e: Touches) => void } };
const mockShader = { uniforms: null as null | { get: () => Uniforms } };
const mockMake = jest.fn((_sksl: string): object | null => ({ kind: "effect" }));
let mockFocused = true;

jest.mock("@shopify/react-native-skia", () => {
  const RN = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    Skia: { RuntimeEffect: { Make: (s: string) => mockMake(s) } },
    Canvas: ({ children, ...p }: { children?: React.ReactNode }) => <RN.View {...p}>{children}</RN.View>,
    Fill: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    Shader: (p: { uniforms: { get: () => Uniforms } }) => {
      mockShader.uniforms = p.uniforms;
      return null;
    },
  };
});
jest.mock("react-native-gesture-handler", () => ({
  GestureDetector: ({ children }: { children: React.ReactNode }) => children,
  useManualGesture: (config: typeof mockGesture.config) => {
    mockGesture.config = config;
    return config;
  },
}));
jest.mock("react-native-worklets", () => ({ scheduleOnRN: (fn: (...a: unknown[]) => void, ...args: unknown[]) => fn(...args) }));
jest.mock("expo-router/react-navigation", () => ({ useIsFocused: () => mockFocused }));
jest.mock("react-native-reanimated", () => {
  const base = jest.requireActual("../test/reanimated");
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    __esModule: true,
    ...base,
    // Shared values that live across renders, with `modify` (the shared double makes a new one each render).
    useSharedValue: <T,>(initial: T) => {
      const ref = React.useRef<{ value: T; get: () => T; set: (v: T) => void; modify: (f: (v: T) => T) => void } | null>(null);
      if (!ref.current) {
        const sv = {
          value: initial,
          get: () => sv.value,
          set: (v: T) => {
            sv.value = v;
          },
          modify: (f: (v: T) => T) => {
            sv.value = f(sv.value);
          },
        };
        ref.current = sv;
      }
      return ref.current;
    },
    useFrameCallback: (cb: (i: FrameInfo) => void) => {
      mockFrame.callback = cb;
      return { setActive: mockFrame.setActive, isActive: false, callbackId: 1 };
    },
  };
});

let reduceMotion = false;
let appStateListener: ((s: string) => void) | null = null;

beforeEach(() => {
  reduceMotion = false;
  mockFocused = true;
  mockFrame.callback = null;
  mockFrame.setActive.mockReset();
  mockGesture.config = null;
  mockShader.uniforms = null;
  jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockImplementation(async () => reduceMotion);
  jest.spyOn(AccessibilityInfo, "isReduceTransparencyEnabled").mockImplementation(async () => false);
  jest.spyOn(AccessibilityInfo, "isDarkerSystemColorsEnabled").mockImplementation(async () => false);
  jest.spyOn(AccessibilityInfo, "addEventListener").mockImplementation(() => ({ remove: () => undefined }) as never);
  Object.defineProperty(AppState, "currentState", { value: "active", configurable: true });
  jest.spyOn(AppState, "addEventListener").mockImplementation((_type, fn) => {
    appStateListener = fn as (s: string) => void;
    return { remove: () => undefined } as never;
  });
});

function tree() {
  const { LiveHero } = require("@/features/entry/live-liquid");
  return (
    <LiveHero testID="hero" fallback={<Text>respaldo</Text>}>
      <Text>Tus clientes, siempre accesibles</Text>
    </LiveHero>
  );
}

async function mount() {
  await render(tree());
  await act(async () => undefined); // the system answers «Reducir movimiento»
  await fireEvent(screen.getByTestId("hero"), "layout", { nativeEvent: { layout: { x: 0, y: 0, width: 400, height: 420 } } });
}

const frame = (ms: number | null) => act(() => mockFrame.callback!({ timestamp: 0, timeSincePreviousFrame: ms, timeSinceFirstFrame: 0 }));
const lastActive = () => mockFrame.setActive.mock.calls.at(-1)?.[0];

describe("the live liquid", () => {
  it("is decoration over the hero: the canvas takes no touches and is hidden from assistive tech", async () => {
    await mount();
    const canvas = screen.getByTestId("liquid-canvas", { includeHiddenElements: true });
    expect(canvas.props.pointerEvents).toBe("none");
    expect(canvas.props.accessible).toBe(false);
    expect(screen.queryByTestId("liquid-canvas")).toBeNull(); // hidden by its layer
    expect(screen.getByText("Tus clientes, siempre accesibles")).toBeTruthy();
  });

  it("runs when it may: motion allowed, screen in focus, app in front, a size", async () => {
    await mount();
    expect(lastActive()).toBe(true);
    expect(mockGesture.config?.enabled).toBe(true);
    // R is the hero in points, the canvas's own units.
    await frame(16);
    expect(mockShader.uniforms!.get().R).toEqual([400, 420]);
  });

  it("a touch takes the liquid there and opens a wave from that point (R5.3)", async () => {
    await mount();
    await frame(16);
    await act(() => mockGesture.config!.onTouchesDown!({ changedTouches: [{ x: 100, y: 105 }] }));
    await frame(16);
    const u = mockShader.uniforms!.get();
    // The model's coordinates: 0–1, y upwards.
    expect(u.W.slice(0, 2).map((v) => Number(v.toFixed(4)))).toEqual([0.25, 0.75]);
    expect(u.W[3]).toBe(1);
    // Dragging moves the pointer toward the finger without another wave.
    for (let i = 0; i < 30; i++) await frame(16);
    await act(() => mockGesture.config!.onTouchesMove!({ changedTouches: [{ x: 300, y: 315 }] }));
    for (let i = 0; i < 30; i++) await frame(16);
    const later = mockShader.uniforms!.get();
    expect(later.P[0]).toBeGreaterThan(0.6);
    expect(later.P[1]).toBeLessThan(0.4);
    expect(later.W.slice(4, 8)).toEqual([0, 0, -99, 0]);
  });

  it("with «Reducir movimiento»: one still frame, and it does not react (R5.2)", async () => {
    reduceMotion = true;
    await mount();
    expect(mockFrame.setActive).not.toHaveBeenCalledWith(true);
    expect(mockGesture.config?.enabled).toBe(false);
    const u = mockShader.uniforms!.get();
    expect(u.T).toBe(STILL_T);
    expect(u.P[2]).toBe(0.35);
    expect(u.W).toEqual(Array(16).fill(-99));
  });

  it("stops when the screen loses focus, and when the app goes to the background", async () => {
    await mount();
    expect(lastActive()).toBe(true);
    mockFocused = false;
    await screen.rerender(tree());
    expect(lastActive()).toBe(false);
    mockFocused = true;
    await screen.rerender(tree());
    expect(lastActive()).toBe(true);
    await act(() => appStateListener!("background"));
    expect(lastActive()).toBe(false);
  });

  it("freezes on the still frame after 30 frames in a row under 50 fps, past the warm-up (R22.4)", async () => {
    await mount();
    for (let i = 0; i < WARMUP_FRAMES; i++) await frame(80);
    expect(lastActive()).toBe(true);
    for (let i = 0; i < 29; i++) await frame(33);
    expect(lastActive()).toBe(true);
    await frame(33);
    expect(lastActive()).toBe(false);
    expect(mockShader.uniforms!.get().T).toBe(STILL_T);
    expect(mockGesture.config?.enabled).toBe(false);
  });
});

describe("when Skia refuses the shader", () => {
  it("the still ground stays: never a hole, never an error", async () => {
    await jest.isolateModulesAsync(async () => {
      mockMake.mockImplementationOnce(() => null);
      const { LiveHero } = require("@/features/entry/live-liquid");
      await render(
        <LiveHero fallback={<Text>respaldo</Text>}>
          <Text>Tus clientes</Text>
        </LiveHero>,
      );
      expect(screen.getByText("respaldo")).toBeTruthy();
      expect(screen.queryByTestId("liquid-canvas", { includeHiddenElements: true })).toBeNull();
    });
  });
});
