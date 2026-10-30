/**
 * Pure rules of the WhatsApp template composer. No React, no network: the
 * dialog asks these what to show, and the tests pin them. Every rule here
 * mirrors something Meta refuses, so the partner learns it before sending,
 * not from a rejection a day later.
 */

export const LIMITS = { name: 512, header: 60, body: 1024, footer: 60, button: 25, buttons: 3, example: 200 } as const;

/** Variables Meta understands: ``{{nombre}}`` (named) or ``{{1}}`` (positional). */
const VAR_RE = /\{\{\s*([a-z0-9_]+)\s*\}\}/g;
/** Anything between double braces, well formed or not. */
const ANY_BRACES_RE = /\{\{([^}]*)\}\}/g;

/** Pure: the body variables, in order of first appearance, without repeats. */
export function templateVariables(body: string): string[] {
  const out: string[] = [];
  for (const match of body.matchAll(VAR_RE)) {
    const name = match[1];
    if (name && !out.includes(name)) out.push(name);
  }
  return out;
}

/**
 * Pure: what the partner types as a name, made into one Meta accepts.
 * «Revisión de pago» → «revision_de_pago». A trailing underscore survives
 * while typing so the next word can follow.
 */
export function toTemplateName(raw: string): string {
  return raw
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[\s-]+/g, "_")
    .replace(/[^a-z0-9_]/g, "")
    .replace(/_{2,}/g, "_")
    .replace(/^_+/, "")
    .slice(0, LIMITS.name);
}

/** Pure: a name ready to send (no trailing underscore). */
export function finalTemplateName(raw: string): string {
  return toTemplateName(raw).replace(/_+$/, "");
}

export type BodyIssue =
  | { code: "starts_with_variable" }
  | { code: "ends_with_variable" }
  | { code: "adjacent_variables" }
  | { code: "mixed_formats" }
  | { code: "bad_variable"; text: string }
  | { code: "positional_gap"; missing: number };

/** Pure: what Meta would refuse in the body, in the order a person would fix it. */
export function bodyIssues(body: string): BodyIssue[] {
  const issues: BodyIssue[] = [];
  const text = body.trim();
  if (!text) return issues;

  for (const match of text.matchAll(ANY_BRACES_RE)) {
    const inner = (match[1] ?? "").trim();
    if (!/^[a-z0-9_]+$/.test(inner)) issues.push({ code: "bad_variable", text: match[0] });
  }
  const vars = templateVariables(text);
  if (vars.length === 0) return issues;

  if (/^\{\{\s*[a-z0-9_]+\s*\}\}/.test(text)) issues.push({ code: "starts_with_variable" });
  if (/\{\{\s*[a-z0-9_]+\s*\}\}[.!?…\s]*$/.test(text)) issues.push({ code: "ends_with_variable" });
  if (/\}\}\s*\{\{/.test(text)) issues.push({ code: "adjacent_variables" });

  const numeric = vars.filter((v) => /^\d+$/.test(v));
  if (numeric.length > 0 && numeric.length < vars.length) issues.push({ code: "mixed_formats" });
  if (numeric.length === vars.length) {
    const nums = numeric.map(Number).sort((a, b) => a - b);
    for (let i = 1; i <= nums.length; i += 1) {
      if (!nums.includes(i)) {
        issues.push({ code: "positional_gap", missing: i });
        break;
      }
    }
  }
  return issues;
}

/** Pure: insert ``{{name}}`` at the cursor, with a space on each side when needed. */
export function insertVariable(body: string, cursor: number, name: string): { text: string; cursor: number } {
  const at = Math.max(0, Math.min(cursor, body.length));
  const before = body.slice(0, at);
  const after = body.slice(at);
  const left = before.length > 0 && !/\s$/.test(before) ? " " : "";
  const right = after.length > 0 && !/^[\s.,;:!?]/.test(after) ? " " : "";
  const token = `${left}{{${name}}}${right}`;
  return { text: before + token + after, cursor: before.length + token.length - right.length };
}

export type PreviewPart = { kind: "text"; value: string } | { kind: "variable"; name: string; value: string | null };

/** Pure: the body cut into text and variables, each variable with its example if any. */
export function previewParts(text: string, examples: Record<string, string>): PreviewPart[] {
  const parts: PreviewPart[] = [];
  let last = 0;
  for (const match of text.matchAll(VAR_RE)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: "text", value: text.slice(last, start) });
    const name = match[1] ?? "";
    const value = (examples[name] ?? "").trim();
    parts.push({ kind: "variable", name, value: value || null });
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", value: text.slice(last) });
  return parts;
}

export type ButtonDraft = { type: "QUICK_REPLY" | "URL" | "PHONE_NUMBER"; label: string; url?: string; phone_number?: string };

export type ButtonIssue = "label_missing" | "url_invalid" | "phone_invalid";

/** Pure: what is wrong with one button, if anything. */
export function buttonIssue(button: ButtonDraft): ButtonIssue | null {
  if (!button.label.trim()) return "label_missing";
  if (button.type === "URL" && !/^https:\/\/[^\s.]+\.[^\s]+$/.test((button.url ?? "").trim())) return "url_invalid";
  if (button.type === "PHONE_NUMBER" && !/^\+\d{8,15}$/.test((button.phone_number ?? "").replace(/[\s-]/g, ""))) return "phone_invalid";
  return null;
}

export type MissingPiece = "name" | "body" | "examples" | "buttons" | "body_rules";

/** Pure: what still stops the template from being sent, to say it next to the button. */
export function missingPieces(input: {
  name: string;
  body: string;
  examples: Record<string, string>;
  buttons: ButtonDraft[];
}): MissingPiece[] {
  const out: MissingPiece[] = [];
  if (!finalTemplateName(input.name)) out.push("name");
  if (!input.body.trim()) out.push("body");
  if (templateVariables(input.body).some((v) => !(input.examples[v] ?? "").trim())) out.push("examples");
  if (bodyIssues(input.body).length > 0) out.push("body_rules");
  if (input.buttons.some((b) => buttonIssue(b) !== null)) out.push("buttons");
  return out;
}

export const LANGUAGES = [
  { code: "es", label: "Español" },
  { code: "es_CL", label: "Español de Chile" },
  { code: "es_MX", label: "Español de México" },
  { code: "es_ES", label: "Español de España" },
  { code: "en", label: "English" },
  { code: "pt_BR", label: "Português do Brasil" },
] as const;

export const SUGGESTED_VARIABLES = ["nombre", "pedido", "fecha", "total"] as const;

/** What the composer starts from when a template is duplicated to fix it. */
export type TemplateDraft = {
  name: string;
  language: string;
  category: "UTILITY" | "MARKETING";
  header: string;
  body: string;
  footer: string;
  buttons: ButtonDraft[];
  examples: Record<string, string>;
};

const text = (v: unknown): string => (typeof v === "string" ? v : "");

/**
 * Pure: Meta's `components` of a template → a draft for the composer (QA
 * 2026-10-30: a rejected template could only be read truncated, never fixed).
 * The name gets `_v2` (Meta keeps the rejected one's name); examples come from
 * named or positional params when Meta returns them.
 */
export function draftFromComponents(row: {
  name: string;
  language: string;
  category: string | null;
  components: Array<Record<string, unknown>>;
}): TemplateDraft {
  const draft: TemplateDraft = {
    name: `${row.name}_v2`.slice(0, LIMITS.name),
    language: row.language,
    category: row.category === "MARKETING" ? "MARKETING" : "UTILITY",
    header: "",
    body: "",
    footer: "",
    buttons: [],
    examples: {},
  };
  for (const c of row.components ?? []) {
    const type = text(c.type).toUpperCase();
    if (type === "HEADER" && text(c.format).toUpperCase() === "TEXT") draft.header = text(c.text);
    if (type === "FOOTER") draft.footer = text(c.text);
    if (type === "BODY") {
      draft.body = text(c.text);
      const example = (c.example ?? {}) as Record<string, unknown>;
      const named = example.body_text_named_params;
      if (Array.isArray(named)) {
        for (const p of named as Array<Record<string, unknown>>) {
          if (text(p.param_name)) draft.examples[text(p.param_name)] = text(p.example);
        }
      }
      const positional = example.body_text;
      if (Array.isArray(positional) && Array.isArray(positional[0])) {
        (positional[0] as unknown[]).forEach((v, i) => {
          draft.examples[String(i + 1)] = text(v);
        });
      }
    }
    if (type === "BUTTONS" && Array.isArray(c.buttons)) {
      for (const b of c.buttons as Array<Record<string, unknown>>) {
        const bt = text(b.type).toUpperCase();
        if (bt === "QUICK_REPLY") draft.buttons.push({ type: "QUICK_REPLY", label: text(b.text) });
        if (bt === "URL") draft.buttons.push({ type: "URL", label: text(b.text), url: text(b.url) });
        if (bt === "PHONE_NUMBER") draft.buttons.push({ type: "PHONE_NUMBER", label: text(b.text), phone_number: text(b.phone_number) });
      }
    }
  }
  return draft;
}

/** Pure: a language code as people read it (`es_CL` → «Español de Chile»). */
export function languageLabel(code: string): string {
  return LANGUAGES.find((l) => l.code === code)?.label ?? code;
}
