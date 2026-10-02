import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { type MessageKey, t as translate } from "@/i18n/messages";
import type { HomeSpend, HomeAttention, HomeTrend } from "@/lib/backend/home-usage";

import { AttentionBlock } from "../attention-block";
import { ConversationsChart } from "../conversations-chart";
import { SpendCard } from "../spend-card";

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);
const n = (v: number) => String(v);

describe("Necesita tu atención", () => {
  it("lists each problem with the button that fixes it, worst first", () => {
    const attention: HomeAttention = {
      clients_ok: 1,
      items: [
        { kind: "out_of_quota", severity: 1, external_client_ref: "flor", client_name: "Flor y Encanto", count: null, href: "/usage?client=flor" },
        { kind: "failed_messages", severity: 5, external_client_ref: "demo", client_name: null, count: 3, href: "/clients/demo/conversations" },
      ],
    };
    render(<AttentionBlock attention={attention} total={3} t={t} n={n} />);
    expect(screen.getByRole("heading", { name: /Necesita tu atención/ })).toBeTruthy();
    expect(screen.getByText("Flor y Encanto")).toBeTruthy();
    expect(screen.getByText("3 mensajes no se entregaron en 24 horas")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Asignar saldo" }).getAttribute("href")).toBe("/usage?client=flor");
    expect(screen.getByRole("button", { name: "Ver conversaciones" }).getAttribute("href")).toBe("/clients/demo/conversations");
    expect(screen.getByText("1 de 3 clientes sin problemas.")).toBeTruthy();
  });

  it("a problem shared by many clients is one row with one fix", () => {
    const items = ["a", "b", "c", "d", "e"].map((ref) => ({
      kind: "out_of_quota" as const,
      severity: 1,
      external_client_ref: ref,
      client_name: ref.toUpperCase(),
      count: null,
      href: `/usage?client=${ref}`,
    }));
    render(<AttentionBlock attention={{ items, clients_ok: 0 }} total={5} t={t} n={n} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("5 clientes")).toBeTruthy();
    expect(screen.getByText("A, B, C y 2 más")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Asignar saldo" }).getAttribute("href")).toBe("/usage");
  });

  it("more than two actions in the list: each row folds them behind three dots", async () => {
    const one = (ref: string, kind: "no_active_agent" | "whatsapp_disconnected" | "failed_messages", severity: number) => ({
      kind,
      severity,
      external_client_ref: ref,
      client_name: ref.toUpperCase(),
      count: 2,
      href: `/clients/${ref}/fix`,
    });
    render(<AttentionBlock attention={{ items: [one("a", "no_active_agent", 2), one("b", "whatsapp_disconnected", 3), one("c", "failed_messages", 5)], clients_ok: 0 }} total={3} t={t} n={n} />);
    expect(screen.queryByRole("button", { name: "Publicar agente" })).toBeNull();
    expect(screen.getByRole("link", { name: "A" }).getAttribute("href")).toBe("/clients/a/fix");
    await userEvent.click(screen.getByRole("button", { name: "Opciones de A" }));
    expect(await screen.findByRole("menuitem", { name: "Publicar agente" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Abrir ficha del cliente" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Ver conversaciones" })).toBeTruthy();
  });

  it("with nothing to fix says so in one calm line", () => {
    render(<AttentionBlock attention={{ items: [], clients_ok: 4 }} total={4} t={t} n={n} />);
    expect(screen.getByRole("status").textContent).toContain("Todos tus clientes están atendiendo");
    expect(screen.queryByRole("heading")).toBeNull();
  });
});

describe("Conversaciones por día", () => {
  it("without conversations says so instead of an empty chart", () => {
    const trend: HomeTrend = { days: ["2026-10-01", "2026-10-02"], series: [0, 0], current: 0, previous: null, by_client: [] };
    render(
      <LocaleProvider locale="es">
        <ConversationsChart trend={trend} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Sin conversaciones en los últimos 7 días.")).toBeTruthy();
  });
});

describe("Gasto del mes", () => {
  const spend: HomeSpend = {
    cents: 1240,
    previous_cents: 1000,
    projected_cents: 3844,
    currency: "USD",
    by_client: [
      { kind: "client", external_client_ref: "a", client_name: "Flor y Encanto", cents: 900 },
      { kind: "outside", external_client_ref: null, client_name: null, cents: 340 },
    ],
  };

  it("says the month in money and who it goes to, nothing more", () => {
    render(<SpendCard spend={spend} t={t} locale="es" />);
    expect(screen.getByLabelText(/12,40/)).toBeTruthy();
    expect(screen.getByText("Flor y Encanto")).toBeTruthy();
    expect(screen.getByText("Companion y pruebas")).toBeTruthy();
    expect(screen.getByText("73 %")).toBeTruthy();
    expect(screen.queryByText(/créditos|millón/)).toBeNull();
    expect(screen.queryByText(/mes pasado|a este ritmo/i)).toBeNull();
  });

  it("without spend says so", () => {
    render(<SpendCard spend={{ ...spend, cents: 0, previous_cents: null, projected_cents: 0, by_client: [] }} t={t} locale="es" />);
    expect(screen.getByText("Todavía no hay gasto este mes.")).toBeTruthy();
  });
});

describe("Conversaciones por día · barras", () => {
  it("one bar per day, today named, the average said, and each day's busiest clients", () => {
    const trend: HomeTrend = {
      days: ["2026-10-01", "2026-10-02"],
      series: [10, 4],
      current: 14,
      previous: null,
      by_client: [{ external_client_ref: "a", client_name: "Flor y Encanto", series: [6, 4] }],
    };
    render(
      <LocaleProvider locale="es">
        <ConversationsChart trend={trend} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Media 7 al día")).toBeTruthy();
    expect(screen.getByText("Hoy")).toBeTruthy();
    expect(screen.getAllByRole("listitem").filter((li) => li.querySelector("[tabindex]"))).toHaveLength(2);
    expect(screen.getByLabelText(/jueves 1: 10 conversaciones/)).toBeTruthy();
    expect(screen.getAllByText("Flor y Encanto")).toHaveLength(2);
  });
});
