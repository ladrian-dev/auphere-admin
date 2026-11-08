import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

const h = vi.hoisted(() => ({
  toast: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  signOut: vi.fn(async () => undefined),
}));
vi.mock("sonner", () => ({ toast: h.toast }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: h.replace, refresh: h.refresh }) }));
vi.mock("@/lib/auth-actions", () => ({ signOutAction: h.signOut }));

const { SessionExpiryNotice } = await import("../session-expiry-notice");

const NOW = new Date("2026-11-07T10:00:00Z").getTime();
const HOUR = 60 * 60 * 1000;
const at = (ms: number) => new Date(NOW + ms).toISOString();

function mount(expiresAt: string | null) {
  return render(
    <LocaleProvider locale="es">
      <SessionExpiryNotice expiresAt={expiresAt} />
    </LocaleProvider>,
  );
}

/**
 * Spec 056 (15.1, 15.2): the session expires 7 days after signing in, without
 * renewing itself. With less than 24 hours left the console says so once, in a
 * toast that blocks nothing, with «Volver a entrar».
 */
describe("SessionExpiryNotice", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    vi.setSystemTime(NOW);
    window.localStorage.clear();
    h.toast.mockReset();
    h.replace.mockReset();
    h.signOut.mockClear();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("with 23 hours left it warns at once, with «Volver a entrar»", async () => {
    mount(at(23 * HOUR));
    expect(h.toast).toHaveBeenCalledTimes(1);
    const [text, options] = h.toast.mock.calls[0]!;
    expect(text).toBe("Tu sesión caduca en menos de un día. Vuelve a entrar para seguir sin cortes.");
    expect(options.action.label).toBe("Volver a entrar");
    await act(async () => options.action.onClick());
    expect(h.signOut).toHaveBeenCalled();
    expect(h.replace).toHaveBeenCalledWith("/login");
  });

  it("with 3 days left it says nothing now, and warns when the last day starts", () => {
    mount(at(72 * HOUR));
    expect(h.toast).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(47 * HOUR));
    expect(h.toast).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(2 * HOUR));
    expect(h.toast).toHaveBeenCalledTimes(1);
  });

  it("mounted again for the same session, it does not repeat", () => {
    const expiresAt = at(5 * HOUR);
    const first = mount(expiresAt);
    first.unmount();
    mount(expiresAt);
    expect(h.toast).toHaveBeenCalledTimes(1);
  });

  it("a new session warns again on its own last day", () => {
    mount(at(5 * HOUR)).unmount();
    mount(at(6 * HOUR));
    expect(h.toast).toHaveBeenCalledTimes(2);
  });

  it("without a date, or with an expired one, nothing", () => {
    mount(null).unmount();
    mount(at(-HOUR)).unmount();
    mount("no es una fecha");
    expect(h.toast).not.toHaveBeenCalled();
  });

  it("without storage (a private window) it still warns, once per mount", () => {
    const broken = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => mount(at(2 * HOUR))).not.toThrow();
    expect(h.toast).toHaveBeenCalledTimes(1);
    broken.mockRestore();
    vi.restoreAllMocks();
  });
});
