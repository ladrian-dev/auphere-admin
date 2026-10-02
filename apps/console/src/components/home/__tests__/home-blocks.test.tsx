import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { type MessageKey, t as translate } from "@/i18n/messages";
import type { HomeAttention, HomeToReview, HomeTrend, PortfolioRow } from "@/lib/backend/home-usage";

import { ActivityFeed } from "../activity-feed";
import { AttentionBlock } from "../attention-block";
import { ConversationsChart } from "../conversations-chart";
import { PortfolioTable } from "../portfolio-table";
import { ReviewBlock } from "../review-block";

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
    expect(screen.getByRole("button", { name: "Asignar crédito" }).getAttribute("href")).toBe("/usage?client=flor");
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
    expect(screen.getByRole("button", { name: "Asignar crédito" }).getAttribute("href")).toBe("/usage");
  });

  it("with nothing to fix says so in one calm line", () => {
    render(<AttentionBlock attention={{ items: [], clients_ok: 4 }} total={4} t={t} n={n} />);
    expect(screen.getByRole("status").textContent).toContain("Todos tus clientes están atendiendo");
    expect(screen.queryByRole("heading")).toBeNull();
  });
});

describe("Por revisar ahora", () => {
  it("each figure opens the first client where it waits", () => {
    const review: HomeToReview = {
      escalated: 2,
      payments: 1,
      unanswered: 0,
      clients: [
        { external_client_ref: "a", client_name: "A", escalated: 2, payments: 0, unanswered: 0, href: "/clients/a/conversations" },
        { external_client_ref: "b", client_name: "B", escalated: 0, payments: 1, unanswered: 0, href: "/clients/b/conversations" },
      ],
    };
    render(<ReviewBlock review={review} t={t} n={n} />);
    expect(screen.getByRole("link", { name: /Conversaciones escaladas/ }).getAttribute("href")).toBe("/clients/a/conversations");
    expect(screen.getByRole("link", { name: /Pagos por revisar/ }).getAttribute("href")).toBe("/clients/b/conversations");
    expect(screen.queryByRole("link", { name: /Sin responder/ })).toBeNull();
  });

  it("empty says nothing waits", () => {
    render(<ReviewBlock review={{ escalated: 0, payments: 0, unanswered: 0, clients: [] }} t={t} n={n} />);
    expect(screen.getByText("Nada espera a una persona.")).toBeTruthy();
  });
});

describe("Tus clientes", () => {
  const row = (ref: string, attention: number, conversations: number): PortfolioRow => ({
    external_client_ref: ref,
    client_name: ref.toUpperCase(),
    status: "active",
    conversations_7d: conversations,
    series_7d: [0, 0, 0, 0, 0, 0, conversations],
    last_activity_at: null,
    credit_cap: ref === "a" ? 1000 : null,
    credit_remaining: ref === "a" ? 400 : null,
    attention,
    href: `/clients/${ref}`,
  });

  it("puts clients with problems first, then the busiest", () => {
    render(<PortfolioTable rows={[row("a", 0, 9), row("b", 2, 1), row("c", 0, 20)]} t={t} n={n} locale="es" />);
    const names = screen.getAllByRole("link").map((l) => l.textContent);
    expect(names).toEqual(["B", "C", "A"]);
    expect(screen.getByText("2 por resolver")).toBeTruthy();
    expect(screen.getAllByText("Sin asignar")).toHaveLength(2);
    expect(screen.getAllByText("Sin actividad")).toHaveLength(3);
  });
});

describe("Actividad reciente", () => {
  it("shows the summary in words, or a calm empty line", () => {
    const { rerender } = render(<ActivityFeed items={[]} locale="es" empty="Todavía no hay actividad." />);
    expect(screen.getByText("Todavía no hay actividad.")).toBeTruthy();
    rerender(
      <ActivityFeed
        items={[{ id: "1", at: new Date().toISOString(), actor: "x", action: "agent.publish", target: "t", external_client_ref: "a", client_name: "A", summary: "Daniela publicó la versión 9 de A" }]}
        locale="es"
        empty="-"
      />,
    );
    expect(screen.getByText("Daniela publicó la versión 9 de A")).toBeTruthy();
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
