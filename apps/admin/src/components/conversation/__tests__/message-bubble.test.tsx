import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MessageOut } from "@/lib/backend";

import { MessageBubble } from "../message-bubble";

const _BASE_INBOUND: MessageOut = {
  id: "msg_1",
  conversation_id: "conv_1",
  created_at: "2026-05-24T16:00:00Z",
  direction: "inbound",
  content: "Hola",
  intent: null,
  cost_usd: null,
  latency_ms: null,
  model: null,
  trace_id: null,
  tool_calls: [],
  status: "delivered",
  delivered_at: null,
  read_at: null,
  failed_at: null,
  failure_code: null,
  last_error: null,
  attempts: 0,
  provider_message_id: null,
  pricing_category: null,
  media_kind: null,
  media_mime: null,
  media_filename: null,
  media_size_bytes: null,
  media_transcript: null,
  reaction_emoji: null,
  reaction_target_wamid: null,
  context_message_id: null,
  interactive_payload: null,
  outcome_overall: null,
  outcome_retries: null,
  outcome_feedback: null,
  actor_kind: null,
  actor_id: null,
};

function outbound(overrides: Partial<MessageOut> = {}): MessageOut {
  return {
    ..._BASE_INBOUND,
    id: overrides.id ?? "msg_out_1",
    direction: "outbound",
    content: overrides.content ?? "Listo, te confirmo.",
    intent: "book",
    model: "anthropic/claude-sonnet-4-6",
    status: overrides.status ?? "sent",
    ...overrides,
  };
}

describe("MessageBubble — direction + header", () => {
  it("renders inbound message with cliente label", () => {
    render(<MessageBubble message={_BASE_INBOUND} />);
    expect(screen.getByText(/← Cliente/)).toBeInTheDocument();
    expect(screen.getByText("Hola")).toBeInTheDocument();
  });

  it("renders outbound message with intent and model in header", () => {
    render(<MessageBubble message={outbound()} />);
    expect(screen.getByText(/→ Agente/)).toBeInTheDocument();
    expect(screen.getByText(/book/)).toBeInTheDocument();
    expect(screen.getByText(/anthropic\/claude-sonnet-4-6/)).toBeInTheDocument();
  });

  it("shows status badge for outbound but not inbound", () => {
    const { rerender } = render(<MessageBubble message={_BASE_INBOUND} />);
    // Inbound: status is "delivered" but the badge should not render.
    expect(screen.queryByText("Entregado")).not.toBeInTheDocument();
    rerender(<MessageBubble message={outbound({ status: "delivered" })} />);
    expect(screen.getByText("Entregado")).toBeInTheDocument();
  });
});

describe("MessageBubble — interactive payload (B1)", () => {
  it("renders buttons interactive as chips", () => {
    const message = outbound({
      content: "Listo, ¿confirmas?",
      interactive_payload: {
        body: "¿Confirmas la reserva?",
        buttons: [
          { id: "yes", title: "Sí" },
          { id: "no", title: "No" },
        ],
      },
    });
    render(<MessageBubble message={message} />);
    expect(screen.getByTestId("interactive-preview")).toBeInTheDocument();
    const chips = screen.getAllByTestId("interactive-button");
    expect(chips.map((c) => c.textContent)).toEqual(["Sí", "No"]);
    expect(screen.getByText("¿Confirmas la reserva?")).toBeInTheDocument();
  });

  it("renders list interactive showing up to 6 items + 'more' line", () => {
    const message = outbound({
      content: "",
      interactive_payload: {
        body: "Elige una opción",
        list: {
          button: "Ver opciones",
          items: Array.from({ length: 8 }, (_, i) => ({
            id: `i${i}`,
            title: `Opción ${i + 1}`,
            description: i === 0 ? "primera" : undefined,
          })),
        },
      },
    });
    render(<MessageBubble message={message} />);
    const items = screen.getAllByTestId("interactive-list-item");
    expect(items).toHaveLength(6);
    expect(screen.getByText(/\+2 más/)).toBeInTheDocument();
    // First item shows description.
    expect(items[0].textContent).toContain("primera");
  });

  it("renders cta_url with button text + URL", () => {
    const message = outbound({
      content: "",
      interactive_payload: {
        body: "Pagás aquí:",
        cta_url: { text: "Pagar pedido", url: "https://shop.example/c/abc" },
      },
    });
    render(<MessageBubble message={message} />);
    expect(screen.getByTestId("interactive-cta-url")).toHaveTextContent(
      "Pagar pedido",
    );
    expect(screen.getByText("https://shop.example/c/abc")).toBeInTheDocument();
  });

  it("shows header and footer when set", () => {
    const message = outbound({
      content: "",
      interactive_payload: {
        body: "Cuerpo",
        header: "Reserva",
        footer: "Expira en 5 min",
        buttons: [{ id: "a", title: "OK" }],
      },
    });
    render(<MessageBubble message={message} />);
    expect(screen.getByText("Reserva")).toBeInTheDocument();
    expect(screen.getByText("Expira en 5 min")).toBeInTheDocument();
  });
});

describe("MessageBubble — outcome grader badge (B3)", () => {
  it("renders pass badge", () => {
    render(
      <MessageBubble
        message={outbound({ outcome_overall: "pass", outcome_retries: 0 })}
      />,
    );
    expect(screen.getByTestId("outcome-badge-pass")).toHaveTextContent("Pass");
  });

  it("renders fail badge with retry count", () => {
    render(
      <MessageBubble
        message={outbound({
          outcome_overall: "fail",
          outcome_retries: 2,
          outcome_feedback: "Falta tool_result que respalde la confirmación.",
        })}
      />,
    );
    const badge = screen.getByTestId("outcome-badge-fail");
    expect(badge).toHaveTextContent("Fail");
    expect(badge.textContent).toContain("r2");
  });

  it("skips badge when outcome_overall is null", () => {
    render(<MessageBubble message={outbound({ outcome_overall: null })} />);
    expect(screen.queryByTestId(/outcome-badge-/)).not.toBeInTheDocument();
  });
});

describe("MessageBubble — tool calls panel (B2)", () => {
  it("renders one entry per tool call with status color", () => {
    const message = outbound({
      tool_calls: [
        {
          tool: "woocommerce.list_products",
          status: "ok",
          result: { products: [{ id: 1, name: "Producto" }] },
        },
        {
          tool: "booking.create_appointment",
          status: "error",
          error: "connector_timeout",
          result: {},
        },
      ],
    });
    render(<MessageBubble message={message} />);
    const entries = screen.getAllByTestId("tool-call-entry");
    expect(entries).toHaveLength(2);
    expect(entries[0]).toHaveTextContent("woocommerce.list_products");
    expect(entries[1]).toHaveTextContent("connector_timeout");
  });

  it("does not render panel when there are no tool calls", () => {
    render(<MessageBubble message={outbound()} />);
    expect(screen.queryByTestId("tool-calls-panel")).not.toBeInTheDocument();
  });
});

describe("MessageBubble — media preview (B1)", () => {
  it("renders icon + filename + size for image", () => {
    const message = outbound({
      media_kind: "image",
      media_filename: "catalogo.jpg",
      media_mime: "image/jpeg",
      media_size_bytes: 524288,
      content: "[image]",
    });
    render(<MessageBubble message={message} />);
    expect(screen.getByTestId("media-preview-image")).toBeInTheDocument();
    expect(screen.getByText("catalogo.jpg")).toBeInTheDocument();
    expect(screen.getByText(/image\/jpeg/)).toBeInTheDocument();
    expect(screen.getByText(/512 kB/)).toBeInTheDocument();
  });

  it("renders transcript collapsible when present", () => {
    const message = outbound({
      media_kind: "audio",
      media_filename: "nota.ogg",
      media_mime: "audio/ogg",
      media_size_bytes: 18000,
      media_transcript: "Hola, quería preguntar por las máquinas",
    });
    render(<MessageBubble message={message} />);
    expect(screen.getByText("Transcripción")).toBeInTheDocument();
  });
});

describe("MessageBubble — footer telemetry (B5)", () => {
  it("renders latency and cost when present", () => {
    render(
      <MessageBubble
        message={outbound({ latency_ms: 423, cost_usd: 0.0042 })}
      />,
    );
    expect(screen.getByText(/423 ms/)).toBeInTheDocument();
    expect(screen.getByText(/\$0.0042/)).toBeInTheDocument();
  });

  it("renders failure_code when message failed", () => {
    render(
      <MessageBubble
        message={outbound({
          status: "failed",
          failure_code: "131047",
          last_error: "outside 24h window",
        })}
      />,
    );
    expect(screen.getByText(/err:131047/)).toBeInTheDocument();
  });

  it("does not render footer when there is no telemetry", () => {
    const { container } = render(<MessageBubble message={_BASE_INBOUND} />);
    // The footer has a border-t class; assert no such div exists.
    expect(container.querySelector(".border-t")).toBeNull();
  });
});

describe("MessageBubble — reactions and quoted replies", () => {
  it("renders reaction line", () => {
    render(
      <MessageBubble
        message={outbound({
          reaction_emoji: "👍",
          reaction_target_wamid: "wamid.HBgL_target_xyz_long",
          content: "[reaction]",
        })}
      />,
    );
    expect(screen.getByTestId("reaction-line")).toHaveTextContent("👍");
    // Component truncates wamid to 16 chars; assert the visible prefix.
    expect(screen.getByText(/wamid.HBgL_targe/)).toBeInTheDocument();
  });

  it("renders quoted reply chip", () => {
    render(
      <MessageBubble
        message={outbound({
          context_message_id: "wamid.HBgL_original_message_xyz_quoted",
        })}
      />,
    );
    expect(screen.getByText(/respondiendo a/)).toBeInTheDocument();
  });
});
