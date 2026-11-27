import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { InboxDetail } from "@/lib/backend/inbox";

import { ContactPanel } from "../contact-panel";
import { ThreadHeader } from "../thread-header";
import { NOW, detail } from "./fixtures";

/**
 * Spec 082 (5.4): con nombre de usuario de WhatsApp, el panel del contacto y la
 * cabecera de la conversación lo enseñan como «@usuario». Sin él, no se pinta
 * nada que lo eche en falta (constitución §V).
 */

function header(d: InboxDetail) {
  return render(
    <LocaleProvider locale="es">
      <ThreadHeader
        detail={d}
        initials="AT"
        busy={false}
        panelOpen={false}
        onBack={vi.fn()}
        onUnread={vi.fn()}
        onResolve={vi.fn()}
        onReopen={vi.fn()}
        onTogglePanel={vi.fn()}
        onClearChat={vi.fn()}
        onDeleteChat={vi.fn()}
      />
    </LocaleProvider>,
  );
}

function panel(d: InboxDetail) {
  return render(
    <LocaleProvider locale="es">
      <ContactPanel
        detail={d}
        initials="AT"
        suggested={[]}
        now={NOW}
        onClose={vi.fn()}
        onTags={vi.fn(async () => true)}
        onNote={vi.fn(async () => true)}
      />
    </LocaleProvider>,
  );
}

function withUsername(username: string | null): InboxDetail {
  const d = detail();
  return { ...d, contact: { ...d.contact, username } };
}

describe("@usuario de WhatsApp", () => {
  it("la cabecera lo enseña junto al nombre", () => {
    header(withUsername("ana.rz"));
    expect(screen.getByText("@ana.rz")).toBeInTheDocument();
  });

  it("el panel del contacto lo enseña bajo el nombre", () => {
    panel(withUsername("ana.rz"));
    expect(screen.getByText("@ana.rz")).toBeInTheDocument();
  });

  it("si ya trae la arroba, no la repite", () => {
    header(withUsername("@ana.rz"));
    expect(screen.getByText("@ana.rz")).toBeInTheDocument();
    expect(screen.queryByText("@@ana.rz")).toBeNull();
  });

  it("sin nombre de usuario no se pinta ninguna arroba", () => {
    const h = header(withUsername(null));
    expect(h.container.textContent).not.toContain("@");
    h.unmount();
    const p = panel(withUsername(null));
    expect(p.container.textContent).not.toContain("@");
  });
});
