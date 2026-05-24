import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  AgentConfig,
  AvailableSkill,
  RuntimeCapabilitiesInput,
} from "@/lib/backend";

import { RuntimeCapabilities } from "../runtime-capabilities";

const _BASE_CONFIG: AgentConfig = {
  id: "cfg_1",
  tenant_id: "tnt_1",
  version: 1,
  status: "staged",
  system_prompt_rendered: "be honest",
  channels: [],
  tools: [],
  policies: {},
  seed_template_ref: null,
  kg_schema_id: null,
  promoted_at: null,
  created_at: "2026-05-24T00:00:00Z",
  updated_at: "2026-05-24T00:00:00Z",
  runtime_memory_tool: false,
  runtime_outcome_grader: false,
  runtime_mcp_connector: false,
  runtime_skills: null,
  runtime_mcp_servers: null,
};

const SKILL_WHATSAPP: AvailableSkill = {
  name: "whatsapp-native-components",
  description: "Choose buttons / list / cta_url vs text on WhatsApp.",
  local_version: "1",
  skill_id: "skill_wa",
  uploaded_version: "v1",
};

const SKILL_GENERIC: AvailableSkill = {
  name: "anti-hallucination-booking",
  description: "Never affirm a booking without a tool result.",
  local_version: "1",
  skill_id: "skill_anti",
  uploaded_version: "v1",
};

const SKILL_NOT_UPLOADED: AvailableSkill = {
  name: "future-skill",
  description: "Future, unuploaded.",
  local_version: "1",
  skill_id: null,
  uploaded_version: null,
};

function makeStagedConfig(
  overrides: Partial<AgentConfig> = {},
): AgentConfig {
  return { ..._BASE_CONFIG, ...overrides };
}

function captureAction() {
  const calls: RuntimeCapabilitiesInput[] = [];
  const action = vi.fn(async (_tid: string, _v: number, body: RuntimeCapabilitiesInput) => {
    calls.push(body);
    return { ok: true as const, data: _BASE_CONFIG };
  });
  return { action, calls };
}

describe("RuntimeCapabilities — channel gating per skill", () => {
  it("hydrates the channel-gate UI from the saved config", () => {
    const config = makeStagedConfig({
      runtime_skills: [
        {
          skill_id: "skill_wa",
          version: "v1",
          channels: ["whatsapp"],
        },
        { skill_id: "skill_anti", version: "v1" },
      ],
    });
    render(
      <RuntimeCapabilities
        tenantId="tnt_1"
        config={config}
        availableSkills={[SKILL_WHATSAPP, SKILL_GENERIC]}
        updateAction={vi.fn() as never}
      />,
    );
    // whatsapp-native-components row should show WhatsApp as the only
    // gated channel.
    const wabutton = screen.getByTestId("channel-toggle-skill_wa-whatsapp");
    expect(wabutton.className).toContain("bg-primary");
    const webButton = screen.getByTestId("channel-toggle-skill_wa-web");
    expect(webButton.className).not.toContain("bg-primary");
    // anti-hallucination has no channel-gate set → expect "sin filtro" hint
    expect(screen.getByText(/sin filtro/)).toBeInTheDocument();
  });

  it("ticking a whatsapp-* skill pre-selects the WhatsApp channel", async () => {
    const config = makeStagedConfig();
    render(
      <RuntimeCapabilities
        tenantId="tnt_1"
        config={config}
        availableSkills={[SKILL_WHATSAPP]}
        updateAction={vi.fn() as never}
      />,
    );
    // Tick the skill.
    await userEvent.click(screen.getByRole("checkbox", { name: "whatsapp-native-components" }));
    // WhatsApp pill should be active (primary background); web should not.
    const wabutton = screen.getByTestId("channel-toggle-skill_wa-whatsapp");
    expect(wabutton.className).toContain("bg-primary");
    const webButton = screen.getByTestId("channel-toggle-skill_wa-web");
    expect(webButton.className).not.toContain("bg-primary");
  });

  it("ticking a non-whatsapp skill defaults to 'all channels' (no filter)", async () => {
    const config = makeStagedConfig();
    render(
      <RuntimeCapabilities
        tenantId="tnt_1"
        config={config}
        availableSkills={[SKILL_GENERIC]}
        updateAction={vi.fn() as never}
      />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "anti-hallucination-booking" }));
    // No channel button should be active.
    const wabutton = screen.getByTestId("channel-toggle-skill_anti-whatsapp");
    expect(wabutton.className).not.toContain("bg-primary");
    // "sin filtro" hint visible.
    expect(screen.getByText(/sin filtro/)).toBeInTheDocument();
  });

  it("toggling a channel pill flips its state without affecting siblings", async () => {
    const config = makeStagedConfig();
    render(
      <RuntimeCapabilities
        tenantId="tnt_1"
        config={config}
        availableSkills={[SKILL_WHATSAPP]}
        updateAction={vi.fn() as never}
      />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "whatsapp-native-components" }));
    // Pre: WhatsApp is on, Web is off.
    await userEvent.click(
      screen.getByTestId("channel-toggle-skill_wa-instagram"),
    );
    // Post: WhatsApp + Instagram on, Web still off.
    expect(
      screen.getByTestId("channel-toggle-skill_wa-whatsapp").className,
    ).toContain("bg-primary");
    expect(
      screen.getByTestId("channel-toggle-skill_wa-instagram").className,
    ).toContain("bg-primary");
    expect(
      screen.getByTestId("channel-toggle-skill_wa-web").className,
    ).not.toContain("bg-primary");
  });

  it("save sends channels only when non-empty", async () => {
    const config = makeStagedConfig();
    const { action, calls } = captureAction();
    render(
      <RuntimeCapabilities
        tenantId="tnt_1"
        config={config}
        availableSkills={[SKILL_WHATSAPP, SKILL_GENERIC]}
        updateAction={action}
      />,
    );
    // Tick whatsapp skill (auto-gates to WhatsApp) AND the generic one
    // (no gate).
    await userEvent.click(screen.getByRole("checkbox", { name: "whatsapp-native-components" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "anti-hallucination-booking" }));
    await userEvent.click(screen.getByRole("button", { name: /Guardar/i }));
    expect(action).toHaveBeenCalledTimes(1);
    expect(calls).toHaveLength(1);
    const sent = calls[0].runtime_skills;
    // whatsapp-* carries channels; generic skill does NOT (back-compat,
    // omitted to mean "all channels").
    const waRef = sent.find((s) => s.skill_id === "skill_wa");
    const antiRef = sent.find((s) => s.skill_id === "skill_anti");
    expect(waRef?.channels).toEqual(["whatsapp"]);
    expect(antiRef?.channels).toBeUndefined();
  });

  it("non-uploaded skills are disabled and never reach the channel UI", () => {
    const config = makeStagedConfig();
    render(
      <RuntimeCapabilities
        tenantId="tnt_1"
        config={config}
        availableSkills={[SKILL_NOT_UPLOADED]}
        updateAction={vi.fn() as never}
      />,
    );
    const checkbox = screen.getByRole("checkbox", { name: "future-skill" });
    // The shadcn Checkbox wraps base-ui — disabled state surfaces as
    // ``data-disabled="true"`` rather than the native ``disabled`` attr.
    expect(checkbox).toHaveAttribute("data-disabled");
    // The channel picker only renders when a skill is selected. The
    // disabled-and-unchecked future-skill must not show one.
    expect(screen.queryByText(/Limitar a canales/)).not.toBeInTheDocument();
  });

  it("non-staged config disables the channel pills", () => {
    const active = makeStagedConfig({
      status: "active",
      runtime_skills: [
        { skill_id: "skill_wa", version: "v1", channels: ["whatsapp"] },
      ],
    });
    render(
      <RuntimeCapabilities
        tenantId="tnt_1"
        config={active}
        availableSkills={[SKILL_WHATSAPP]}
        updateAction={vi.fn() as never}
      />,
    );
    const wabutton = screen.getByTestId(
      "channel-toggle-skill_wa-whatsapp",
    ) as HTMLButtonElement;
    expect(wabutton).toBeDisabled();
  });
});

describe("RuntimeCapabilities — dirty tracking", () => {
  it("changing only the channel-gate of an already-selected skill enables Save", async () => {
    const config = makeStagedConfig({
      runtime_skills: [
        { skill_id: "skill_wa", version: "v1", channels: ["whatsapp"] },
      ],
    });
    render(
      <RuntimeCapabilities
        tenantId="tnt_1"
        config={config}
        availableSkills={[SKILL_WHATSAPP]}
        updateAction={vi.fn() as never}
      />,
    );
    const saveButton = screen.getByRole("button", { name: /Guardar/i });
    expect(saveButton).toBeDisabled();
    // Add a second channel — should now be dirty.
    await userEvent.click(
      screen.getByTestId("channel-toggle-skill_wa-instagram"),
    );
    expect(saveButton).not.toBeDisabled();
  });
});

// Silence the unused-import warning when this file is read by future
// agents — the helper isn't referenced because all factories live above.
void within;
