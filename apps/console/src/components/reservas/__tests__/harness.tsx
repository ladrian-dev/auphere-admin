import { render } from "@testing-library/react";
import type * as React from "react";
import { vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { toasts } from "./toasts";

import type { ReservasData } from "../context";
import { NOW_ISO, TODAY } from "../model/__tests__/fixtures";
import type { ReservasUrl } from "../model/url-state";
import type { ReservasInitial } from "../reservas-view";

/**
 * Spec 043: renders the whole Reservas screen with its Server Actions as
 * mocks (`a`), the router as a spy and the toasts captured. Each test file
 * mocks the three modules with these before importing the view:
 *
 *   vi.mock("@/app/(console)/reservas/actions", async () => (await import("./harness")).a);
 *   vi.mock("next/navigation", async () => (await import("./harness")).navigation);
 *   vi.mock("sonner", async () => (await import("./toasts")).sonner);
 */
export const a = {
  bookingDetailAction: vi.fn(),
  serviceSlotsAction: vi.fn(),
  capacitySlotsAction: vi.fn(),
  cancelPreviewAction: vi.fn(),
  createBookingAction: vi.fn(),
  moveBookingAction: vi.fn(),
  cancelBookingAction: vi.fn(),
  bookingTransitionAction: vi.fn(),
  walkinAction: vi.fn(),
  createBlockAction: vi.fn(),
  removeBlockAction: vi.fn(),
  addWaitlistAction: vi.fn(),
  removeWaitlistAction: vi.fn(),
  offerWaitlistAction: vi.fn(),
  stopOfferAction: vi.fn(),
  patchSettingsAction: vi.fn(),
  putBusinessHoursAction: vi.fn(),
  createStaffAction: vi.fn(),
  updateStaffAction: vi.fn(),
  archiveStaffAction: vi.fn(),
  createServiceAction: vi.fn(),
  updateServiceAction: vi.fn(),
  archiveServiceAction: vi.fn(),
};

export const router = { push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() };
export const navigation = {
  useRouter: () => router,
  usePathname: () => "/reservas",
  useSearchParams: () => new URLSearchParams(),
};

export { sonner, toasts } from "./toasts";

export function resetMocks() {
  for (const fn of Object.values(a)) fn.mockReset();
  for (const fn of Object.values(router)) fn.mockReset();
  toasts.success.mockReset();
  toasts.error.mockReset();
  a.cancelPreviewAction.mockResolvedValue({ ok: true, data: { can_offer: false, candidates: 0, why_not: "waitlist_off" } });
}

export const ViewRef: { current: React.ComponentType<{ initial: ReservasInitial }> | null } = { current: null };

export function url(o: Partial<ReservasUrl> = {}): ReservasUrl {
  return { tab: "agenda", view: "grid", period: "day", date: TODAY, staff: null, ...o };
}

export function renderView(
  data: ReservasData | null,
  o: { url?: Partial<ReservasUrl>; errors?: string[]; hasInbox?: boolean; locale?: "es" | "en"; booking?: string | null } = {},
) {
  const View = ViewRef.current!;
  return render(
    <LocaleProvider locale={o.locale ?? "es"}>
      <View initial={{ url: url(o.url), nowIso: NOW_ISO, data, errors: o.errors ?? [], hasInbox: o.hasInbox ?? true, booking: o.booking ?? null }} />
    </LocaleProvider>,
  );
}
