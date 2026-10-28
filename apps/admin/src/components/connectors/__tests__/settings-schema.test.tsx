import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SettingsFields } from "../settings-fields";
import { settingsFields } from "../settings-schema";

/** The schema of Amigable (`services/connectors/catalog.py`, `SETTINGS_SCHEMAS`). */
const AMIGABLE = {
  type: "object",
  additionalProperties: false,
  required: ["business_uuid"],
  properties: {
    business_uuid: { type: "string", minLength: 1 },
    base_url: { type: "string", pattern: "^https://" },
    reminders: {
      type: "object",
      additionalProperties: false,
      properties: {
        enabled: { type: "boolean" },
        hour_local: { type: "integer", minimum: 0, maximum: 23 },
      },
    },
  },
};

/** Spec 047 (T172; 36.2, 36.4): the settings an integration asks for, from its schema. */
describe("an integration's settings", () => {
  it("reads every setting, with its groups flattened, its type and its rules", () => {
    expect(settingsFields(AMIGABLE)).toEqual([
      { key: "business_uuid", type: "Texto", required: true, rules: ["No puede ir vacío"] },
      { key: "base_url", type: "Texto", required: false, rules: ["Empieza por https://"] },
      { key: "reminders.enabled", type: "Sí o no", required: false, rules: [] },
      { key: "reminders.hour_local", type: "Número entero", required: false, rules: ["De 0 a 23"] },
    ]);
    expect(settingsFields({ properties: { store_url: { type: "string", format: "uri", pattern: "^https://" } } })[0]!.rules).toEqual([
      "Una URL",
      "Empieza por https://",
    ]);
    expect(settingsFields(null)).toEqual([]);
  });

  it("shows them in a table, and says when there are none", () => {
    const { unmount } = render(<SettingsFields schema={AMIGABLE} />);
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(5);
    expect(within(rows[1]!).getByText("business_uuid")).toBeTruthy();
    expect(within(rows[1]!).getByText("Obligatorio")).toBeTruthy();
    expect(within(rows[4]!).getByText("De 0 a 23")).toBeTruthy();
    unmount();
    render(<SettingsFields schema={null} />);
    expect(screen.getByText("No pide ajustes")).toBeTruthy();
  });
});
