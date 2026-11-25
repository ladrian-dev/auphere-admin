/**
 * Spec 079, criterio 2.2: tras un rechazo por permiso, la página vuelve con
 * `?sin-permiso=1`. El aviso lo dice una vez y quita el parámetro sin recargar.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

let search = "";
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/partners/p-1",
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ replace }),
}));

const { PermissionDeniedNotice } = await import("../permission-denied-notice");

beforeEach(() => {
  search = "";
  replace.mockReset();
});

describe("PermissionDeniedNotice (spec 079, 2.2)", () => {
  it("con ?sin-permiso=1 avisa de que no se hizo nada y quita el parámetro", () => {
    search = "tab=wallet&sin-permiso=1";
    render(<PermissionDeniedNotice />);
    const notice = screen.getByRole("status");
    expect(notice.textContent).toContain("Tu rol no permite esa acción; no se hizo nada.");
    expect(replace).toHaveBeenCalledWith("/partners/p-1?tab=wallet", { scroll: false });
  });

  it("sin el parámetro no pinta nada", () => {
    search = "tab=wallet";
    render(<PermissionDeniedNotice />);
    expect(screen.queryByRole("status")).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });
});
