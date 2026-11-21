import { fireEvent, render, screen } from "@testing-library/react-native";

/**
 * Spec 069 (R20.1, R1.4; design §3.3): «No es cliente» and «Sin acceso» keep
 * what they do (spec 031, R1.5 and R1.6) with the design's look — the icon
 * tile, the title in the display style, a few words and the way back. Still
 * no way into the partner console from this app (031, 2026-10-20).
 */
const mockReplace = jest.fn();
jest.mock("expo-router", () => ({ router: { replace: (...a: unknown[]) => mockReplace(...a), back: jest.fn(), push: jest.fn() } }));
jest.mock("expo-image", () => ({ Image: () => null }));

beforeEach(() => mockReplace.mockReset());

describe.each([
  ["not-a-client", "Esta app es para los negocios que atiende Auphere"],
  ["no-access", "Tu negocio no tiene acceso a la app"],
])("%s", (route, title) => {
  it("has its tile, its title as the screen's header in the display style, and «Entrar con otra cuenta»", async () => {
    const Screen = require(`@/app/${route}`).default;
    await render(<Screen />);
    expect(screen.getByTestId("entry-tile", { includeHiddenElements: true })).toBeTruthy();
    const header = screen.getByRole("header", { name: title });
    expect(header.props.style).toEqual(expect.arrayContaining([expect.objectContaining({ fontSize: 28, fontWeight: "600" })]));
    await fireEvent.press(screen.getByRole("button", { name: "Entrar con otra cuenta" }));
    expect(mockReplace).toHaveBeenCalledWith("/sign-in");
    expect(screen.queryByRole("button", { name: /consola/i })).toBeNull();
  });
});
