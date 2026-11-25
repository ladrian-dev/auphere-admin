import { fireEvent, render, screen } from "@testing-library/react-native";
import { readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";
import { Linking } from "react-native";

import { STORE_URL } from "@/config";
import { attachChoices } from "@/features/inbox/model";
import { t as translate, type T } from "@/i18n/t";
import { routeFor } from "@/push/routing";
import { type } from "@/theme/type";

/**
 * Spec 069, the second analyze pass (S1, S2): what a ticked task promised a
 * test for and had none. R1.6 (no weight above 600) and, from Requisito 20,
 * «Actualizar» when the version is retired — its screen, not only the event.
 */
jest.mock("expo-router", () => ({ router: { replace: jest.fn(), back: jest.fn(), push: jest.fn() } }));
jest.mock("expo-image", () => ({ Image: () => null }));
jest.mock("@/auth/session", () => ({ useSession: () => ({ state: { status: "update-required", reason: "Seguridad" } }) }));

function sources(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) sources(path, out);
    else if (/\.tsx?$/.test(name)) out.push(path);
  }
  return out;
}

describe("no weight above 600 (R1.6, T011)", () => {
  it("in every style of the scale", () => {
    for (const [name, style] of Object.entries(type)) {
      const w = Number(style.fontWeight ?? 400);
      expect({ name, ok: w <= 600 }).toEqual({ name, ok: true });
    }
  });

  it("anywhere in the app's code, both platforms' tables included", () => {
    const heavy = /fontWeight:\s*["']?(?:700|800|900|bold)\b|weight\(\s*["']?(?:700|800|900|bold)\b/;
    const offenders = sources(join(__dirname, "..", "src")).filter((f) => heavy.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });
});

describe("«Actualizar» when the version is retired (R20.1, spec 031 R13.1)", () => {
  it("says why, and its one button opens the store", async () => {
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
    const Screen = require("@/app/update-required").default;
    await render(<Screen />);
    expect(screen.getByRole("header", { name: "Actualiza Auphere Customers" })).toBeTruthy();
    expect(screen.getByText("Seguridad")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Actualizar" }));
    expect(open).toHaveBeenCalledWith(STORE_URL);
  });
});

describe("attachments from the camera, the gallery and documents (R20.1)", () => {
  const t: T = (k, v) => translate("es", k, v);
  it("the menu offers the three, each to its own source", () => {
    expect(attachChoices(t)).toEqual([
      { label: "Hacer una foto", source: "camera" },
      { label: "Elegir de la galería", source: "library" },
      { label: "Elegir un PDF", source: "document" },
    ]);
  });
});

describe("the seven kinds of notice open where they belong (R20.1)", () => {
  const C = "3f1c2a7e-8b9d-4e5f-a1b2-c3d4e5f6a7b8";
  it.each([
    ["inbox.waiting", `auphere-customers://inbox/${C}`, `/conversacion/${C}`],
    ["inbox.message_for_you", `auphere-customers://inbox/${C}`, `/conversacion/${C}`],
    ["client.balance", "auphere-customers://usage", "/consumo"],
    ["reservas.agent_change", "auphere-customers://reservas/r-2026-10-23-17", "/reservas?open=r-2026-10-23-17"],
    ["reservas.cancelled_today", "auphere-customers://reservas/r-2026-10-23-18", "/reservas?open=r-2026-10-23-18"],
    ["reservas.waitlist_accepted", "auphere-customers://reservas/r-2026-10-23-19", "/reservas?open=r-2026-10-23-19"],
    ["agents.state", "auphere-customers://home", "/"],
  ])("%s", (kind, url, route) => {
    expect(routeFor({ url, kind })).toBe(route);
  });
});
