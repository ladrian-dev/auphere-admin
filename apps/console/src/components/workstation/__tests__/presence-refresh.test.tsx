/**
 * Requisito 8.1 (spec 002) — la presencia se ve sin recargar a mano.
 */
import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { PresenceRefresh } from "../presence-refresh";

describe("PresenceRefresh", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    refresh.mockClear();
  });

  it("refresca con la cadencia del latido mientras la pestaña está visible", () => {
    render(<PresenceRefresh intervalMs={1000} />);
    vi.advanceTimersByTime(3100);
    expect(refresh).toHaveBeenCalledTimes(3);
  });

  it("y deja de hacerlo al desmontar", () => {
    const { unmount } = render(<PresenceRefresh intervalMs={1000} />);
    unmount();
    vi.advanceTimersByTime(3000);
    expect(refresh).not.toHaveBeenCalled();
  });
});
