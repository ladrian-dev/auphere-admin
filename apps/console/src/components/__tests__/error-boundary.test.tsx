import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { RouteError, ViewerKindProvider } from "../error-boundary";

/** What Next puts in `error.message` in production: its own words, in English. */
const NEXT_TEXT = "An error occurred in the Server Components render. The specific message is omitted in production builds to avoid leaking sensitive details.";

function view(kind: "client" | "partner" | null, error: Error & { digest?: string }, locale: "es" | "en" = "es") {
  const reset = vi.fn();
  const body = <RouteError error={error} reset={reset} />;
  render(<LocaleProvider locale={locale}>{kind ? <ViewerKindProvider kind={kind}>{body}</ViewerKindProvider> : body}</LocaleProvider>);
  return reset;
}

/**
 * Spec 056 (10.1): a screen that fails to load says so in the person's language
 * and offers Reintentar. Never the technical message: not to a client person,
 * and not to anyone once Next has given it a digest (it is Next's sentence).
 */
describe("RouteError", () => {
  it("a client person never reads the error's message", async () => {
    const reset = view("client", Object.assign(new Error("Backend 500 at https://api.staging/console/lite/reservas"), {}));
    expect(screen.getByText("No se pudo cargar esta pantalla")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Backend 500");
    expect(document.body.textContent).not.toContain("https://");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(reset).toHaveBeenCalled();
  });

  it("with a digest, nobody does: it is Next's sentence, in English", () => {
    view("partner", Object.assign(new Error(NEXT_TEXT), { digest: "1234567890" }));
    expect(document.body.textContent).not.toContain("Server Components");
    expect(screen.getByText("No se pudo cargar esta pantalla")).toBeInTheDocument();
  });

  it("outside the console frame (a failed layout), nobody does either", () => {
    view(null, new Error("Backend 502 at https://api"));
    expect(document.body.textContent).not.toContain("Backend 502");
  });

  it("a partner member still reads what the API said, without a digest", () => {
    view("partner", new Error("Backend 409: client_archived"));
    expect(screen.getByText("Backend 409: client_archived")).toBeInTheDocument();
  });

  it("in English, in English", () => {
    view("client", Object.assign(new Error(NEXT_TEXT), { digest: "x" }), "en");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Server Components");
  });
});
