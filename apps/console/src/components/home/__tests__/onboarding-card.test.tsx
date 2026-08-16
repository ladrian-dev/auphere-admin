import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { Onboarding } from "@/lib/backend/onboarding";

import { ONBOARDING_DISMISS_KEY, OnboardingCardClient } from "../onboarding-card-client";

const data: Onboarding = {
  steps: [
    { key: "team", done: true, href: "/team" },
    { key: "first_client", done: true, href: "/clients/new" },
    { key: "agent_published", done: false, href: "/clients/acme/agent" },
    { key: "channel_connected", done: false, href: "/clients/acme/channels" },
    { key: "first_conversation", done: false, href: "/clients/acme/conversations" },
  ],
  done_count: 2,
  total: 5,
  complete: false,
  partner_created_at: "2026-08-01T00:00:00Z",
  activated_at: "2026-08-01T02:00:00Z",
  time_to_first_active_client_seconds: 7200,
};

describe("OnboardingCardClient", () => {
  beforeEach(() => window.localStorage.clear());

  it("renders progress, links pending steps and shows the activation metric", () => {
    render(
      <LocaleProvider locale="es">
        <OnboardingCardClient data={data} role="owner" />
      </LocaleProvider>,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
    expect(screen.getByText("2 de 5 completados")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Publica un agente/ })).toHaveAttribute("href", "/clients/acme/agent");
    expect(screen.queryByRole("link", { name: /Invita a tu equipo/ })).toBeNull(); // done → not a link
    expect(screen.getByText(/2 h/)).toBeInTheDocument();
  });

  it("dismisses into localStorage and hides", async () => {
    const user = userEvent.setup();
    render(
      <LocaleProvider locale="en">
        <OnboardingCardClient data={data} role="analyst" />
      </LocaleProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Hide" }));
    expect(window.localStorage.getItem(ONBOARDING_DISMISS_KEY)).toBe("1");
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("renders the error state and hides when complete", () => {
    const { rerender } = render(
      <LocaleProvider locale="en">
        <OnboardingCardClient data={null} role="owner" />
      </LocaleProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the checklist.");
    rerender(
      <LocaleProvider locale="en">
        <OnboardingCardClient data={{ ...data, complete: true }} role="owner" />
      </LocaleProvider>,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText("Getting started")).toBeNull();
  });
});
