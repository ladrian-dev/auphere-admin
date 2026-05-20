/**
 * Degradation engine.
 *
 * `degrade(ucm, channel)` returns the closest UCM the channel can render.
 *
 * Strategy (declarative, no surprises):
 *   1. If the channel supports the UCM as-is (validation passes), return it.
 *   2. If the channel does not support the capability, fall back to a `text`
 *      UCM whose body is `ucm.fallback_text`. This is the universal escape.
 *   3. If the channel supports the capability but a limit is exceeded:
 *        - quick_replies with too many buttons → degrade to `list` if
 *          `interactive.list` is supported; otherwise to `text` fallback.
 *        - list with too many rows → truncate to the channel limit and add
 *          a synthetic "ver más" row that maps to a text response.
 *        - everything else → degrade to `text` fallback.
 *   4. composite is degraded by recursively degrading each child; if the
 *      depth exceeds the channel limit, the composite is flattened.
 *
 * Degradation never throws. If we cannot produce something valid, we return
 * the text fallback, which every channel supports by contract (or it
 * shouldn't be a channel at all).
 */
import {
  UCMMessageSchema,
  UCM_VERSION,
  type UCMMessage,
} from "./types.js";
import {
  getChannel,
  channelSupports,
  inferCapabilities,
  type ChannelName,
  type ChannelProfile,
} from "./channels/capabilities.js";
import { validate } from "./validators/index.js";

export type DegradationStep = {
  reason: "capability" | "limit" | "depth";
  from: string;
  to: string;
  detail: string;
};

export type DegradeResult = {
  ucm: UCMMessage;
  changed: boolean;
  steps: DegradationStep[];
};

export function degrade(
  input: UCMMessage,
  channel: ChannelName | ChannelProfile,
): DegradeResult {
  const profile = typeof channel === "string" ? getChannel(channel) : channel;
  const steps: DegradationStep[] = [];
  const result = degradeInner(input, profile, steps);
  return {
    ucm: result,
    changed: steps.length > 0,
    steps,
  };
}

function degradeInner(
  ucm: UCMMessage,
  channel: ChannelProfile,
  steps: DegradationStep[],
): UCMMessage {
  // Capability check first — if the channel cannot render this type at all,
  // collapse to text fallback immediately.
  const caps = inferCapabilities(ucm.type, ucm.content as Record<string, unknown>);
  const unsupported = caps.filter((c) => !channelSupports(channel, c));
  if (unsupported.length > 0) {
    steps.push({
      reason: "capability",
      from: ucm.type,
      to: "text",
      detail: `channel "${channel.name}" lacks ${unsupported.join(", ")}`,
    });
    return toTextFallback(ucm);
  }

  // Composite: recurse first, then check depth.
  if (ucm.type === "composite") {
    const limit = channel.limits.compositeMaxDepth;
    if (limit != null && compositeDepth(ucm) > limit) {
      steps.push({
        reason: "depth",
        from: "composite",
        to: "composite (flattened)",
        detail: `depth > ${limit}`,
      });
      const flat = flattenComposite(ucm);
      const childResults = flat.content.children.map((c) =>
        degradeInner(c, channel, steps),
      );
      return { ...flat, content: { children: childResults } };
    }
    const childResults = ucm.content.children.map((c) =>
      degradeInner(c, channel, steps),
    );
    return { ...ucm, content: { children: childResults } };
  }

  // Structural limits: re-use validator and apply per-type fixes.
  const verdict = validate(ucm, channel);
  if (verdict.ok) return ucm;

  // Only proceed with limit-specific fixes; if there's a non-limit issue
  // (shape/capability that wasn't caught) we degrade to text safely.
  const onlyLimits = verdict.issues.every((i) => i.kind === "limit");
  if (!onlyLimits) {
    steps.push({
      reason: "capability",
      from: ucm.type,
      to: "text",
      detail: `validation failed: ${verdict.issues
        .map((i) => `${i.kind}@${i.path}: ${i.message}`)
        .join("; ")}`,
    });
    return toTextFallback(ucm);
  }

  switch (ucm.type) {
    case "quick_replies": {
      const max = channel.limits.quickRepliesMaxButtons ?? Infinity;
      const titleMax = channel.limits.quickRepliesTitleMaxChars ?? Infinity;
      const buttons = ucm.content.buttons.map((b) => ({
        id: b.id,
        title: truncate(b.title, titleMax),
      }));
      // Too many buttons: prefer `list` if available, else text fallback.
      if (buttons.length > max) {
        if (channel.capabilities.has("interactive.list")) {
          steps.push({
            reason: "limit",
            from: "quick_replies",
            to: "list",
            detail: `${buttons.length} buttons > ${max} — converted to list`,
          });
          const list: UCMMessage = {
            ucm_version: UCM_VERSION,
            message_id: `${ucm.message_id}::degraded`,
            type: "list",
            capabilities_required: ["interactive.list"],
            fallback_text: ucm.fallback_text,
            metadata: { ...ucm.metadata, degraded_from: "quick_replies" },
            content: {
              body: ucm.content.body,
              button_text: truncate(
                "Ver opciones",
                channel.limits.listButtonTextMaxChars ?? 20,
              ),
              sections: [
                {
                  title: truncate(
                    "Opciones",
                    channel.limits.listRowTitleMaxChars ?? 24,
                  ),
                  rows: buttons
                    .slice(0, channel.limits.listMaxRowsTotal ?? buttons.length)
                    .map((b) => ({
                      id: b.id,
                      title: truncate(
                        b.title,
                        channel.limits.listRowTitleMaxChars ?? 24,
                      ),
                    })),
                },
              ],
            },
          };
          return list;
        }
        steps.push({
          reason: "limit",
          from: "quick_replies",
          to: "text",
          detail: `${buttons.length} buttons > ${max} — channel cannot list, falling back to text`,
        });
        return toTextFallback(ucm);
      }
      // Truncated titles only.
      const someTruncated = buttons.some(
        (b, i) => b.title !== ucm.content.buttons[i]?.title,
      );
      if (someTruncated) {
        steps.push({
          reason: "limit",
          from: "quick_replies",
          to: "quick_replies (truncated)",
          detail: `button titles truncated to ${titleMax} chars`,
        });
        return { ...ucm, content: { ...ucm.content, buttons } };
      }
      return ucm;
    }
    case "list": {
      const maxRows = channel.limits.listMaxRowsTotal ?? Infinity;
      const rowTitleMax = channel.limits.listRowTitleMaxChars ?? Infinity;
      const rowDescMax = channel.limits.listRowDescriptionMaxChars ?? Infinity;
      const btnTextMax = channel.limits.listButtonTextMaxChars ?? Infinity;

      let count = 0;
      const sections = ucm.content.sections.map((s) => ({
        ...s,
        title: truncate(s.title, rowTitleMax),
        rows: s.rows
          .filter(() => {
            if (count >= maxRows) return false;
            count++;
            return true;
          })
          .map((r) => ({
            ...r,
            title: truncate(r.title, rowTitleMax),
            description:
              r.description != null ? truncate(r.description, rowDescMax) : r.description,
          })),
      }));
      const totalRowsOrig = ucm.content.sections.reduce(
        (acc, s) => acc + s.rows.length,
        0,
      );
      const truncatedRows = totalRowsOrig > maxRows;
      if (truncatedRows) {
        steps.push({
          reason: "limit",
          from: "list",
          to: "list (truncated)",
          detail: `${totalRowsOrig} rows > ${maxRows} — truncated`,
        });
      }
      const newButton = truncate(ucm.content.button_text, btnTextMax);
      if (newButton !== ucm.content.button_text) {
        steps.push({
          reason: "limit",
          from: "list",
          to: "list (truncated button_text)",
          detail: `button_text truncated to ${btnTextMax} chars`,
        });
      }
      return {
        ...ucm,
        content: { ...ucm.content, button_text: newButton, sections },
      };
    }
    case "cta_url": {
      const max = channel.limits.ctaUrlButtonTitleMaxChars ?? Infinity;
      const button_title = truncate(ucm.content.button_title, max);
      if (button_title !== ucm.content.button_title) {
        steps.push({
          reason: "limit",
          from: "cta_url",
          to: "cta_url (truncated button_title)",
          detail: `button_title truncated to ${max} chars`,
        });
      }
      return { ...ucm, content: { ...ucm.content, button_title } };
    }
    case "text":
    case "media": {
      const max = channel.limits.textBodyMaxChars ?? Infinity;
      if (ucm.type === "text") {
        const body = truncate(ucm.content.body, max);
        if (body !== ucm.content.body) {
          steps.push({
            reason: "limit",
            from: "text",
            to: "text (truncated)",
            detail: `body truncated to ${max} chars`,
          });
        }
        return { ...ucm, content: { ...ucm.content, body } };
      }
      // media with too-long caption
      if (ucm.content.caption != null) {
        const caption = truncate(ucm.content.caption, max);
        if (caption !== ucm.content.caption) {
          steps.push({
            reason: "limit",
            from: "media",
            to: "media (truncated caption)",
            detail: `caption truncated to ${max} chars`,
          });
        }
        return { ...ucm, content: { ...ucm.content, caption } };
      }
      return ucm;
    }
    default:
      return ucm;
  }
}

function toTextFallback(ucm: UCMMessage): UCMMessage {
  return {
    ucm_version: UCM_VERSION,
    message_id: `${ucm.message_id}::fallback`,
    type: "text",
    capabilities_required: ["text"],
    fallback_text: ucm.fallback_text,
    metadata: { ...ucm.metadata, degraded_from: ucm.type },
    content: { body: ucm.fallback_text, format: "plain" },
  };
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  if (max <= 1) return s.slice(0, max);
  return s.slice(0, Math.max(1, max - 1)) + "…";
}

function compositeDepth(ucm: UCMMessage): number {
  if (ucm.type !== "composite") return 0;
  let m = 0;
  for (const c of ucm.content.children) {
    m = Math.max(m, compositeDepth(c));
  }
  return 1 + m;
}

function flattenComposite(ucm: UCMMessage): UCMMessage & { type: "composite" } {
  if (ucm.type !== "composite")
    throw new Error("flattenComposite called on non-composite");
  const out: UCMMessage[] = [];
  for (const child of ucm.content.children) {
    if (child.type === "composite") {
      out.push(...flattenComposite(child).content.children);
    } else {
      out.push(child);
    }
  }
  return { ...ucm, content: { children: out } };
}
