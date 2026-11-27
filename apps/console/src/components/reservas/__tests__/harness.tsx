import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type * as React from "react";
import { vi } from "vitest";

import { LiveStreamProvider } from "@/components/live/live-stream";
import { LocaleProvider } from "@/i18n/client";
import { RESERVAS_TEMPLATE_NAMES } from "@/lib/backend/reservas-templates";
import { testQueryClient } from "@/test/query";

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
 *   vi.mock("@/app/(console)/reservas/templates-actions", async () => (await import("./harness")).a);
 *   vi.mock("next/navigation", async () => (await import("./harness")).navigation);
 *   vi.mock("sonner", async () => (await import("./toasts")).sonner);
 */
export const a = {
  // Spec 082: each re-read of the screen (React Query) goes through this action.
  reservasScreenAction: vi.fn(),
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
  patchBusinessHoursAction: vi.fn(),
  createStaffAction: vi.fn(),
  updateStaffAction: vi.fn(),
  archiveStaffAction: vi.fn(),
  createServiceAction: vi.fn(),
  updateServiceAction: vi.fn(),
  archiveServiceAction: vi.fn(),
  connectStaffCalendarAction: vi.fn(),
  refreshStaffCalendarAction: vi.fn(),
  staffCalendarsAction: vi.fn(),
  staffCalendarAction: vi.fn(),
  // Spec 043, requisito 15: `templates-actions.ts`, mocked with this same object
  // (`vi.mock("@/app/(console)/reservas/templates-actions", …)`).
  reservasTemplatesAction: vi.fn(),
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
  // Spec 082: a re-read is asked for and, unless the test says what it brings, never
  // arrives — the screen keeps what it shows, as a slow network would.
  a.reservasScreenAction.mockImplementation(() => new Promise(() => undefined));
  a.cancelPreviewAction.mockResolvedValue({ ok: true, data: { can_offer: false, candidates: 0, why_not: "waitlist_off" } });
  a.reservasTemplatesAction.mockResolvedValue({
    ok: true,
    data: {
      whatsapp: false,
      approved: 0,
      items: RESERVAS_TEMPLATE_NAMES.map((name) => ({ name, state: "not_created", rejection: null, why_not_created: "no_whatsapp", since: null })),
    },
  });
}

export const ViewRef: { current: React.ComponentType<{ initial: ReservasInitial }> | null } = { current: null };

export function url(o: Partial<ReservasUrl> = {}): ReservasUrl {
  return { tab: "agenda", view: "grid", period: "day", date: TODAY, staff: null, ...o };
}

/** What `reservasScreenAction` answers: the screen of `url()` read again at `nowIso`. */
export function screenRead(
  data: ReservasData | null,
  nowIso: string,
  o: { url?: Partial<ReservasUrl>; errors?: string[]; followsToday?: boolean } = {},
) {
  return {
    ok: true as const,
    data: { url: url(o.url), nowIso, data, errors: o.errors ?? [], hasInbox: true, booking: null, followsToday: o.followsToday ?? false },
  };
}

/**
 * Spec 082: the screen reads through React Query, so it renders inside a fresh
 * query cache (one per render) and, with `live`, under the console's shared
 * live line. Both live in the `wrapper`: a `rerender` keeps them.
 */
export function renderView(
  data: ReservasData | null,
  o: {
    url?: Partial<ReservasUrl>;
    errors?: string[];
    hasInbox?: boolean;
    locale?: "es" | "en";
    booking?: string | null;
    live?: boolean;
    client?: QueryClient;
    /** The URL carried no `date`: re-reads ask for the business's today. */
    followsToday?: boolean;
  } = {},
) {
  const View = ViewRef.current!;
  const client = o.client ?? testQueryClient();
  const live = o.live ?? false;
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <LiveStreamProvider enabled={live}>{children}</LiveStreamProvider>
      </QueryClientProvider>
    );
  }
  const view = render(
    <LocaleProvider locale={o.locale ?? "es"}>
      <View
        initial={{
          url: url(o.url),
          nowIso: NOW_ISO,
          data,
          errors: o.errors ?? [],
          hasInbox: o.hasInbox ?? true,
          booking: o.booking ?? null,
          followsToday: o.followsToday ?? false,
        }}
      />
    </LocaleProvider>,
    { wrapper: Wrapper },
  );
  return Object.assign(view, { client });
}
