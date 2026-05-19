import type { UCMMessage } from "@nexus/ucm-schema";

import { bubble, tokens } from "../tokens";
import type { OnInteractiveResponse } from "../types";

type ListUCM = Extract<UCMMessage, { type: "list" }>;

/**
 * Renders a UCM ``list`` message — body + sectioned, selectable rows.
 *
 * Accessibility: the rows form a ``role="listbox"`` per section so a
 * screen reader announces the count and each row's title + description.
 * Each row is a real ``<button>`` so it works with keyboard nav out of
 * the box; arrow-key cycling is delegated to the browser through the
 * default focus order.
 */
export function List({
  ucm,
  onInteractive,
}: {
  ucm: ListUCM;
  onInteractive?: OnInteractiveResponse;
}) {
  return (
    <div
      style={bubble}
      data-ucm-type="list"
      data-ucm-message-id={ucm.message_id}
    >
      {ucm.content.header && (
        <div
          style={{
            fontWeight: 600,
            marginBottom: tokens.spacing / 2,
            color: tokens.textMuted,
            fontSize: 12,
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          {ucm.content.header}
        </div>
      )}
      <div style={{ marginBottom: tokens.spacing }}>{ucm.content.body}</div>
      {ucm.content.sections.map((section, si) => {
        const labelId = `list-${ucm.message_id}-s${si}-label`;
        return (
          <div key={`${ucm.message_id}-s${si}`} style={{ marginTop: tokens.spacing }}>
            <div
              id={labelId}
              style={{
                fontWeight: 600,
                fontSize: 13,
                color: tokens.textMuted,
                marginBottom: tokens.spacing / 2,
              }}
            >
              {section.title}
            </div>
            <ul
              role="listbox"
              aria-labelledby={labelId}
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
                display: "flex",
                flexDirection: "column",
                gap: 4,
              }}
            >
              {section.rows.map((row) => (
                <li key={row.id} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected="false"
                    aria-label={
                      row.description
                        ? `${row.title}. ${row.description}`
                        : row.title
                    }
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: `${tokens.spacing}px ${tokens.spacing * 1.25}px`,
                      background: tokens.surfaceMuted,
                      border: `1px solid ${tokens.border}`,
                      borderRadius: tokens.radiusSm,
                      cursor: "pointer",
                      fontSize: 14,
                      color: tokens.text,
                    }}
                    onClick={() =>
                      onInteractive?.({
                        id: row.id,
                        title: row.title,
                        source: "list",
                      })
                    }
                  >
                    <div style={{ fontWeight: 500 }}>{row.title}</div>
                    {row.description && (
                      <div
                        style={{
                          fontSize: 12,
                          color: tokens.textMuted,
                          marginTop: 2,
                        }}
                      >
                        {row.description}
                      </div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {ucm.content.footer && (
        <div
          style={{
            marginTop: tokens.spacing,
            fontSize: 12,
            color: tokens.textMuted,
          }}
        >
          {ucm.content.footer}
        </div>
      )}
    </div>
  );
}
