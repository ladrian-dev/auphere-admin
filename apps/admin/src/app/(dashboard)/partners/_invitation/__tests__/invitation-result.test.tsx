import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OwnerInvitationResult } from "@/lib/backend";

const resend = vi.fn();
vi.mock("../actions", () => ({ resendOwnerInvitationAction: (...a: unknown[]) => resend(...a) }));

import { InvitationResult } from "../invitation-result";

const base: OwnerInvitationResult = {
  id: "i1",
  email: "duena@acme.test",
  role: "owner",
  status: "pending",
  expires_at: "2026-11-24T19:00:00Z",
  created_at: "2026-11-03T19:00:00Z",
  last_sent_at: "2026-11-03T19:00:01Z",
  email_sent: true,
  accept_url: "https://console.test/invite/tok-viejo",
};
const failed: OwnerInvitationResult = { ...base, email_sent: false, last_sent_at: null };

function Harness({ initial, onDead }: { initial: OwnerInvitationResult; onDead?: (m: string) => void }) {
  const [state, setState] = useState({ result: initial, replaced: false });
  return (
    <InvitationResult
      partnerId="p1"
      partnerName="Acme"
      result={state.result}
      replacedPrevious={state.replaced}
      onReplaced={(result) => setState({ result, replaced: true })}
      onDead={onDead ?? (() => {})}
    />
  );
}

describe("InvitationResult (spec 052, R2)", () => {
  beforeEach(() => {
    resend.mockReset();
  });

  it("when it went out: to whom, until when, and the link as a fallback", () => {
    render(<Harness initial={base} />);
    expect(screen.getByRole("status").textContent).toMatch("Invitación enviada a duena@acme.test");
    expect(document.body.textContent).toMatch("24 de noviembre de 2026");
    expect(screen.getByText("https://console.test/invite/tok-viejo")).toBeTruthy();
    expect(document.body.textContent).toMatch(/por si no le llega/i);
    // Nada que reintentar si salió.
    expect(screen.queryByRole("button", { name: /Reintentar/ })).toBeNull();
  });

  it("never says delivered or received: it only knows the provider took it", () => {
    const { rerender } = render(<Harness initial={base} />);
    expect(document.body.textContent).toMatch(/el proveedor de correo la aceptó/);
    for (const result of [base, failed]) {
      rerender(<Harness key={result.id + result.email_sent} initial={result} />);
      expect(document.body.textContent).not.toMatch(/entregad|recibid/i);
    }
  });

  it("when it did not go out: partner and invitation exist, not again, copy and retry", () => {
    render(<Harness initial={failed} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch("El correo no salió");
    expect(alert.textContent).toMatch("Acme y su invitación existen");
    expect(alert.textContent).toMatch("no se volverá a mostrar");
    expect(screen.getByText("https://console.test/invite/tok-viejo")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Copiar/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reintentar el envío" })).toBeTruthy();
  });

  it("does not go away by itself", () => {
    vi.useFakeTimers();
    try {
      render(<Harness initial={failed} />);
      act(() => {
        vi.advanceTimersByTime(60 * 60 * 1000);
      });
      expect(screen.getByRole("alert").textContent).toMatch("El correo no salió");
    } finally {
      vi.useRealTimers();
    }
  });

  it("retrying replaces the link and says the old one no longer works", async () => {
    resend.mockResolvedValue({
      ok: true,
      data: { ...failed, id: "i2", accept_url: "https://console.test/invite/tok-nuevo" },
    });
    render(<Harness initial={failed} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Reintentar el envío" }));
    expect(await screen.findByText("https://console.test/invite/tok-nuevo")).toBeTruthy();
    expect(screen.queryByText("https://console.test/invite/tok-viejo")).toBeNull();
    expect(document.body.textContent).toMatch(/enlace anterior ya no sirve/);
    expect(resend).toHaveBeenCalledWith("p1", "i1");
  });

  it("a retry that succeeds becomes the sent view, on the new row", async () => {
    resend.mockResolvedValue({ ok: true, data: { ...base, id: "i2", accept_url: "https://console.test/invite/tok-nuevo" } });
    render(<Harness initial={failed} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar el envío" }));
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch("Invitación enviada a duena@acme.test");
    expect(document.body.textContent).toMatch(/enlace anterior ya no sirve/);
  });

  it("a refused retry keeps the link it has and says why", async () => {
    resend.mockResolvedValue({ ok: false, code: "console_off", error: "La consola de este partner está apagada." });
    render(<Harness initial={failed} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar el envío" }));
    expect(await screen.findByText("La consola de este partner está apagada.")).toBeTruthy();
    expect(screen.getByText("https://console.test/invite/tok-viejo")).toBeTruthy();
  });

  it("an invitation that died hands over to whoever shows the tab", async () => {
    const onDead = vi.fn();
    resend.mockResolvedValue({ ok: false, code: "invitation_accepted", error: "Esa persona ya aceptó la invitación." });
    render(<Harness initial={failed} onDead={onDead} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar el envío" }));
    await vi.waitFor(() => expect(onDead).toHaveBeenCalledWith("Esa persona ya aceptó la invitación."));
  });

  it("a retry whose answer was lost does not leave a link that may be dead", async () => {
    // El reenvío pudo confirmarse: el enlace en pantalla ya estaría muerto.
    const onDead = vi.fn();
    resend.mockResolvedValue({ ok: false, code: "unknown_outcome", error: "No pudimos confirmar el resultado." });
    render(<Harness initial={failed} onDead={onDead} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar el envío" }));
    await vi.waitFor(() => expect(onDead).toHaveBeenCalled());
    expect(onDead.mock.calls[0]?.[0]).toMatch(/puede que el enlace .* ya no sirva/);
  });

  it("blocks the retry while the request lasts", async () => {
    let answer: (v: unknown) => void = () => {};
    resend.mockReturnValue(new Promise((r) => (answer = r)));
    render(<Harness initial={failed} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Reintentar el envío" }));
    const busy = await screen.findByRole("button", { name: /Reintentando/ });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      answer({ ok: true, data: { ...failed, id: "i2" } });
    });
  });

  it("takes the focus when it appears, and works with the keyboard", async () => {
    render(<Harness initial={failed} />);
    const focused = document.activeElement as HTMLElement;
    expect(focused.textContent).toMatch("El correo no salió");
    const user = userEvent.setup();
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Copiar/ }));
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Reintentar el envío" }));
  });

  it("copies the whole link and says so", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<Harness initial={base} />);
    await user.click(screen.getByRole("button", { name: /Copiar/ }));
    expect(writeText).toHaveBeenCalledWith("https://console.test/invite/tok-viejo");
    expect(await screen.findByText("Enlace copiado")).toBeTruthy();
  });

  it("if the clipboard fails it says to select the text", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("no"));
    render(<Harness initial={base} />);
    await user.click(screen.getByRole("button", { name: /Copiar/ }));
    expect(await screen.findByText(/selecciona el enlace/)).toBeTruthy();
  });
});
