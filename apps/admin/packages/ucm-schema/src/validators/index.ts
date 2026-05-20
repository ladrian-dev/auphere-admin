/**
 * Channel-pluggable validation for UCM messages.
 *
 * The schema-level Zod validation in `types.ts` guarantees the SHAPE is valid
 * UCM v1.0.0. The validators in this module check whether a *valid* UCM can be
 * rendered on a specific channel — i.e. capability + structural limits.
 *
 * Two failure modes are reported separately:
 *  - `capability`: the channel does not support this UCM type at all.
 *  - `limit`:      the channel supports the type, but a field exceeds a limit.
 *
 * Capability failures are typically resolved by the degradation engine; limit
 * failures usually indicate a bug in the agent's UCM emission and should be
 * surfaced loudly to the operator during QA.
 */
import { UCMMessageSchema, type UCMMessage } from "../types.js";
import {
  getChannel,
  channelSupports,
  inferCapabilities,
  type ChannelName,
  type ChannelProfile,
} from "../channels/capabilities.js";

export type ValidationIssue = {
  kind: "capability" | "limit" | "shape";
  path: string;
  message: string;
};

export type ValidationResult =
  | { ok: true; ucm: UCMMessage }
  | { ok: false; issues: ValidationIssue[] };

/**
 * Validate `raw` as UCM and check that it can be rendered on `channelName`.
 *
 * `raw` is whatever the agent emitted; it goes through Zod first to catch
 * shape errors, then through the channel-specific limit checks.
 */
export function validate(
  raw: unknown,
  channel: ChannelName | ChannelProfile,
): ValidationResult {
  const parsed = UCMMessageSchema.safeParse(raw);
  if (!parsed.success) {
    return {
      ok: false,
      issues: parsed.error.issues.map((i) => ({
        kind: "shape" as const,
        path: i.path.join(".") || "<root>",
        message: i.message,
      })),
    };
  }
  const ucm = parsed.data;
  const profile = typeof channel === "string" ? getChannel(channel) : channel;
  const issues: ValidationIssue[] = [];
  walkAndCheck(ucm, profile, "<root>", issues);
  return issues.length === 0 ? { ok: true, ucm } : { ok: false, issues };
}

function walkAndCheck(
  ucm: UCMMessage,
  channel: ChannelProfile,
  path: string,
  out: ValidationIssue[],
): void {
  // capability check
  const needed = inferCapabilities(ucm.type, ucm.content as Record<string, unknown>);
  for (const cap of needed) {
    if (!channelSupports(channel, cap)) {
      out.push({
        kind: "capability",
        path,
        message: `channel "${channel.name}" does not support capability "${cap}" required by type "${ucm.type}"`,
      });
    }
  }
  // structural limits per type
  checkLimits(ucm, channel, path, out);
  // recurse composite
  if (ucm.type === "composite") {
    const limit = channel.limits.compositeMaxDepth;
    if (limit != null) {
      const depth = compositeDepth(ucm);
      if (depth > limit) {
        out.push({
          kind: "limit",
          path,
          message: `composite depth ${depth} exceeds channel limit ${limit}`,
        });
      }
    }
    ucm.content.children.forEach((child, idx) => {
      walkAndCheck(child, channel, `${path}.children[${idx}]`, out);
    });
  }
}

function checkLimits(
  ucm: UCMMessage,
  channel: ChannelProfile,
  path: string,
  out: ValidationIssue[],
): void {
  const L = channel.limits;
  const issue = (kind: "limit", msg: string) =>
    out.push({ kind, path, message: msg });

  switch (ucm.type) {
    case "text": {
      if (L.textBodyMaxChars != null && ucm.content.body.length > L.textBodyMaxChars) {
        issue("limit", `text body ${ucm.content.body.length} chars exceeds ${L.textBodyMaxChars}`);
      }
      return;
    }
    case "quick_replies": {
      const c = ucm.content;
      if (L.textBodyMaxChars != null && c.body.length > L.textBodyMaxChars) {
        issue("limit", `quick_replies body exceeds ${L.textBodyMaxChars} chars`);
      }
      if (L.quickRepliesMaxButtons != null && c.buttons.length > L.quickRepliesMaxButtons) {
        issue("limit", `quick_replies has ${c.buttons.length} buttons, channel max ${L.quickRepliesMaxButtons}`);
      }
      if (L.quickRepliesTitleMaxChars != null) {
        c.buttons.forEach((b, i) => {
          if (b.title.length > L.quickRepliesTitleMaxChars!) {
            issue("limit", `quick_replies.buttons[${i}].title length ${b.title.length} > ${L.quickRepliesTitleMaxChars}`);
          }
        });
      }
      return;
    }
    case "list": {
      const c = ucm.content;
      if (L.textBodyMaxChars != null && c.body.length > L.textBodyMaxChars) {
        issue("limit", `list body exceeds ${L.textBodyMaxChars} chars`);
      }
      if (L.listButtonTextMaxChars != null && c.button_text.length > L.listButtonTextMaxChars) {
        issue("limit", `list.button_text exceeds ${L.listButtonTextMaxChars} chars`);
      }
      const totalRows = c.sections.reduce((acc, s) => acc + s.rows.length, 0);
      if (L.listMaxRowsTotal != null && totalRows > L.listMaxRowsTotal) {
        issue("limit", `list has ${totalRows} rows total, channel max ${L.listMaxRowsTotal}`);
      }
      if (L.listRowTitleMaxChars != null || L.listRowDescriptionMaxChars != null) {
        c.sections.forEach((s, si) => {
          s.rows.forEach((r, ri) => {
            if (L.listRowTitleMaxChars != null && r.title.length > L.listRowTitleMaxChars) {
              issue("limit", `list.sections[${si}].rows[${ri}].title exceeds ${L.listRowTitleMaxChars} chars`);
            }
            if (
              L.listRowDescriptionMaxChars != null &&
              r.description != null &&
              r.description.length > L.listRowDescriptionMaxChars
            ) {
              issue("limit", `list.sections[${si}].rows[${ri}].description exceeds ${L.listRowDescriptionMaxChars} chars`);
            }
          });
        });
      }
      return;
    }
    case "cta_url": {
      const c = ucm.content;
      if (L.textBodyMaxChars != null && c.body.length > L.textBodyMaxChars) {
        issue("limit", `cta_url body exceeds ${L.textBodyMaxChars} chars`);
      }
      if (
        L.ctaUrlButtonTitleMaxChars != null &&
        c.button_title.length > L.ctaUrlButtonTitleMaxChars
      ) {
        issue("limit", `cta_url.button_title exceeds ${L.ctaUrlButtonTitleMaxChars} chars`);
      }
      return;
    }
    case "media": {
      if (L.textBodyMaxChars != null && ucm.content.caption != null) {
        if (ucm.content.caption.length > L.textBodyMaxChars) {
          issue("limit", `media caption exceeds ${L.textBodyMaxChars} chars`);
        }
      }
      return;
    }
    case "location":
    case "flow":
    case "composite":
      return;
  }
}

function compositeDepth(ucm: UCMMessage): number {
  if (ucm.type !== "composite") return 0;
  let max = 0;
  for (const child of ucm.content.children) {
    max = Math.max(max, compositeDepth(child));
  }
  return 1 + max;
}

export { getChannel, inferCapabilities };
export type { ChannelName, ChannelProfile };
