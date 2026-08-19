"use client";

import { Check, Copy, LifeBuoy, Route } from "lucide-react";
import * as React from "react";

import { Badge, Button } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { optionalKey } from "./i18n";
import type { SupportPreview, SupportTicket } from "./types";

/**
 * Support — §25.1/§25.2 of the research, §4 of CONTRACT-V2.
 *
 * The Companion never closes a conversation with a "no"; it closes it with
 * a path. Two pieces implement that here:
 *
 * - `SupportProposal`, the `preview` of a `support_help` /
 *   `support_capability` action, shown BEFORE the user confirms;
 * - `TicketRef`, the identifier that comes back in `support.ticket` after
 *   the write, attached to the same card.
 *
 * Both tools are `propose`, not shortcuts: `console.apply` is still the
 * only `mutates` in the catalogue (guarantee C4). Nobody sends a ticket in
 * the partner's name without the partner seeing it.
 */

/**
 * The proposal, before confirming (v2 §4.2).
 *
 * It has its own component rather than falling into the generic key/value
 * `preview` view for one concrete reason: `checked` is a list, and the
 * generic view would render it with `JSON.stringify` — readable to a
 * programmer and rubbish to everyone else. And `checked` is the whole
 * point: it is what stops the ticket reading as a vague complaint, and it
 * comes from the tool catalogue's labels, the same provenance that holds
 * up R1.
 */
export function SupportProposal({ preview }: { preview: SupportPreview }) {
  const t = useT();

  return (
    <div className="mt-2 min-w-0 space-y-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Badge variant="outline" className="shrink-0">
          {t(`companion.support.category.${preview.category}` as const)}
        </Badge>
        <TopicChip topic={preview.topic} />
        {preview.bridge ? (
          // The tint is on the BORDER, not on the words. `--color-status-info`
          // resolves to mint (#2FA98C), which is ~2.9:1 on the card — fine
          // for a graphical edge, well under the 4.5:1 that text owes
          // (WCAG 1.4.3). The label carries the meaning at full contrast
          // and the colour only decorates, which is the rule the rest of
          // this drawer already follows.
          <Badge variant="outline" className="shrink-0 border-status-info/60 text-foreground">
            {t("companion.support.bridge")}
          </Badge>
        ) : null}
      </div>

      {preview.clientRef ? (
        <p className="min-w-0 text-xs text-muted-foreground">
          {t("companion.preview.client_ref")}: <span className="font-mono">{preview.clientRef}</span>
        </p>
      ) : null}

      {preview.need ? (
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{t("companion.support.need")}</p>
          <p className="mt-px text-xs text-pretty break-words text-foreground">{preview.need}</p>
        </div>
      ) : null}

      {/* The list of what the Companion already read. Without it a ticket
          is a ticket with no file behind it, and support starts from
          zero — which is exactly what §25.1 exists to prevent. */}
      {preview.checked.length > 0 ? (
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{t("companion.support.checked")}</p>
          <ul className="mt-px min-w-0 space-y-px">
            {preview.checked.map((item) => (
              <li key={item} className="flex min-w-0 items-start gap-2 text-xs text-foreground">
                <Check aria-hidden="true" className="mt-px size-3 shrink-0 text-status-positive" />
                <span className="min-w-0 text-pretty break-words">{item}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {preview.alternative ? (
        <div className="min-w-0">
          <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <Route aria-hidden="true" className="size-3 shrink-0" />
            {t("companion.support.alternative")}
          </p>
          <p className="mt-px text-xs text-pretty break-words text-foreground">{preview.alternative}</p>
        </div>
      ) : null}

      {/* §25.4: the bridge does NOT replace the ticket. A bridge nobody
          records becomes invisible debt, so we say it in the card. */}
      {preview.bridge ? (
        <p className="text-xs text-pretty text-muted-foreground">{t("companion.support.bridge.body")}</p>
      ) : null}
    </div>
  );
}

/**
 * The ticket reference, after applying (v2 §4.4 / §4.5).
 *
 * `AU-142` is what the person will repeat over the phone, so it is the
 * biggest and the most copyable thing on the card. An identifier you have
 * to select by hand with a mouse is not a usable identifier.
 *
 * `sla` is a stable identifier translated here — the backend does not emit
 * the sentence (§4.4), and we do not derive one from the identifier: it is
 * a table.
 */
export function TicketRef({ ticket }: { ticket: SupportTicket }) {
  const t = useT();
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 2500);
    return () => window.clearTimeout(id);
  }, [copied]);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(ticket.ref);
      setCopied(true);
    } catch {
      // Denied permission or an insecure context. The reference is on
      // screen and selectable, so the feature degrades rather than breaks.
    }
  }

  return (
    <div className="mt-3 min-w-0 rounded-sm border border-border bg-muted p-3">
      <div className="flex min-w-0 items-center gap-2">
        <LifeBuoy aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h4 className="min-w-0 flex-1 text-xs font-medium text-muted-foreground">{t("companion.support.opened")}</h4>
        <Badge variant="outline" className="shrink-0">
          {t(`companion.support.category.${ticket.category}` as const)}
        </Badge>
      </div>

      <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2">
        <span className="min-w-0 font-mono text-lg font-semibold break-all tabular-nums text-foreground select-all">
          {ticket.ref}
        </span>
        <Button variant="ghost" size="icon-sm" aria-label={t("companion.support.copyRef")} onClick={() => void copy()}>
          {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        </Button>
      </div>

      {/* The toast lives in the root layout, outside this modal dialog's
          inert region, so a screen reader would never hear it. Same
          reasoning as `companion.closeBlocked` in CO-03. */}
      <p role="status" aria-live="polite" className="sr-only">
        {copied ? t("companion.support.copied", { ref: ticket.ref }) : ""}
      </p>

      <p className="mt-1 text-xs text-pretty text-muted-foreground">
        {t(`companion.support.sla.${ticket.sla}` as const)}
      </p>

      <div className="mt-2 min-w-0">
        <TopicChip topic={ticket.topic} />
      </div>
    </div>
  );
}

/**
 * `topic` is a stable aggregation SLUG (`connector.shopify`), not prose —
 * it is the key that makes *"seven partners asked for Shopify this
 * quarter"* answerable at all (§4.2).
 *
 * So it is painted as what it is: monospace, inside a labelled chip.
 * Turning `connector.shopify` into a sentence would be inventing wording
 * the backend never sent, and getting it subtly wrong. If we ever know a
 * particular slug, `companion.support.topic.<slug>` overrides it.
 */
function TopicChip({ topic }: { topic: string }) {
  const t = useT();
  if (!topic) return null;
  const known = optionalKey(`companion.support.topic.${topic}`);
  return (
    <span className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-sm border border-border px-2 py-px text-xs">
      <span className="shrink-0 text-muted-foreground">{t("companion.support.topic")}</span>
      {/* `break-all`, not `truncate`: a slug is an identifier and half an
          identifier is useless. It wraps inside the chip instead. */}
      <span className={`min-w-0 break-all ${known ? "text-foreground" : "font-mono text-foreground"}`}>
        {known ? t(known) : topic}
      </span>
    </span>
  );
}
