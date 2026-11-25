/**
 * Pure rules of the WhatsApp template editor. No React, no network: the
 * editor asks these what to show, and the tests pin them. Every rule here
 * mirrors something Meta refuses, so the partner learns it before sending,
 * not from a rejection a day later.
 *
 * Spec 075 (R9): moved from the console to `@nexus/ui` with the editor, so the
 * console and the operator panel say the same thing. What decides whether a
 * template can be edited lives in the API (R3), never here.
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

export type MissingPiece =
  | "name"
  | "body"
  | "examples"
  | "buttons"
  | "body_rules"
  | "system_variables"
  | "otp_button"
  | "otp_minutes";

/** Spec 077 (3.1): what an authentication template lets us choose; Meta fixes the rest. */
export type OtpDraft = { buttonText: string; minutes: string; security: boolean };
export const OTP_LIMITS = { button: 25, minMinutes: 1, maxMinutes: 90 } as const;

/** Empty: no expiry. A whole number 1–90: the minutes. Anything else: invalid. */
export function otpMinutes(text: string): number | null | "invalid" {
  const t = text.trim();
  if (!t) return null;
  if (!/^\d+$/.test(t)) return "invalid";
  const n = Number(t);
  return n >= OTP_LIMITS.minMinutes && n <= OTP_LIMITS.maxMinutes ? n : "invalid";
}

/** Where a new authentication template starts: the caller's default button, ten minutes and the notice. */
export function defaultOtp(buttonText: string): OtpDraft {
  return { buttonText, minutes: "10", security: true };
}

/**
 * Pure: Meta's fixed text of an authentication template, as the customer reads
 * it in Spanish (Meta writes it in the template's language; the sample here is
 * Spanish, so it stands only for a Spanish template: `isSpanishTemplate`). It
 * follows the fields: no security sentence when it is off, no expiry line
 * without valid minutes. One text for the console and the panel (spec 075, 10.3).
 */
export function otpPreviewText(otp: OtpDraft, code = "123456"): { body: string; expiry: string | null } {
  const minutes = otpMinutes(otp.minutes);
  return {
    body: `${code} es tu código de verificación.${otp.security ? " Por tu seguridad, no lo compartas." : ""}`,
    expiry: typeof minutes === "number" ? `Este código caduca en ${minutes} ${minutes === 1 ? "minuto" : "minutos"}.` : null,
  };
}

/** Pure: what still stops an authentication template from being sent. */
export function missingOtpPieces(input: { name: string; otp: OtpDraft }): MissingPiece[] {
  const out: MissingPiece[] = [];
  if (!finalTemplateName(input.name)) out.push("name");
  const button = input.otp.buttonText.trim();
  if (!button || button.length > OTP_LIMITS.button) out.push("otp_button");
  if (otpMinutes(input.otp.minutes) === "invalid") out.push("otp_minutes");
  return out;
}

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
  category: "UTILITY" | "MARKETING" | "AUTHENTICATION";
  /** Spec 077: only with AUTHENTICATION. */
  otp?: OtpDraft;
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
    category:
      row.category === "MARKETING" ? "MARKETING" : row.category === "AUTHENTICATION" ? "AUTHENTICATION" : "UTILITY",
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
  if (draft.category === "AUTHENTICATION") return authenticationDraft(draft, row.components ?? []);
  return draft;
}

/**
 * Spec 077: a rejected authentication template comes back as what can be
 * chosen (button, expiry, security notice) — its body is Meta's, never ours.
 */
function authenticationDraft(draft: TemplateDraft, components: Array<Record<string, unknown>>): TemplateDraft {
  const otp: OtpDraft = { buttonText: "", minutes: "", security: false };
  for (const c of components) {
    const type = text(c.type).toUpperCase();
    if (type === "BODY") otp.security = c.add_security_recommendation === true || /no lo compartas|do not share/i.test(text(c.text));
    if (type === "FOOTER" && typeof c.code_expiration_minutes === "number") otp.minutes = String(c.code_expiration_minutes);
    if (type === "BUTTONS" && Array.isArray(c.buttons)) {
      const button = (c.buttons as Array<Record<string, unknown>>).find((b) => ["OTP", "URL"].includes(text(b.type).toUpperCase()));
      if (button) otp.buttonText = text(button.text);
    }
  }
  return { ...draft, header: "", body: "", footer: "", buttons: [], examples: {}, otp };
}

/**
 * Pure: whether the composer can preview Meta's fixed text of an
 * authentication template — its sample is Spanish, so only for `es`, `es_CL`…
 */
export function isSpanishTemplate(language: string): boolean {
  return language.trim().toLowerCase().startsWith("es");
}

/** Pure: a language code as people read it (`es_CL` → «Español de Chile»). */
export function languageLabel(code: string): string {
  return LANGUAGES.find((l) => l.code === code)?.label ?? code;
}

/** A template with a message of its own (Utility, Marketing): the API's shape, trimmed. */
export type ContentSubmission = {
  name: string;
  language: string;
  category: "UTILITY" | "MARKETING";
  header_text?: string;
  body_text: string;
  footer_text?: string;
  buttons: Array<{ type: ButtonDraft["type"]; label: string; url?: string; phone_number?: string }>;
  /** One example per body variable, and only those. */
  examples: Record<string, string>;
};

/** Spec 077 (3.4): an authentication template carries what can be chosen, never a body. */
export type OtpSubmission = {
  name: string;
  language: string;
  category: "AUTHENTICATION";
  otp_button_text: string;
  /** Left out when the field is empty: no expiry line. */
  otp_expiration_minutes?: number;
  otp_security_recommendation: boolean;
};

/**
 * What the editor hands to whoever saves it, as the console's create action
 * and the API take it (spec 075, 10.5): one shape in both screens.
 */
export type TemplateSubmission = ContentSubmission | OtpSubmission;

/** Pure: a draft → what is sent. An emptied header or footer is left out (the edit replaces it all). */
export function toSubmission(draft: TemplateDraft): TemplateSubmission {
  if (draft.category === "AUTHENTICATION") {
    const otp = draft.otp ?? defaultOtp("");
    const minutes = otpMinutes(otp.minutes);
    return {
      name: finalTemplateName(draft.name),
      language: draft.language,
      category: "AUTHENTICATION",
      otp_button_text: otp.buttonText.trim(),
      ...(typeof minutes === "number" ? { otp_expiration_minutes: minutes } : {}),
      otp_security_recommendation: otp.security,
    };
  }
  return {
    name: finalTemplateName(draft.name),
    language: draft.language,
    category: draft.category,
    header_text: draft.header.trim() || undefined,
    body_text: draft.body.trim(),
    footer_text: draft.footer.trim() || undefined,
    buttons: draft.buttons.map((b) => ({
      type: b.type,
      label: b.label.trim(),
      url: b.type === "URL" ? b.url?.trim() : undefined,
      phone_number: b.type === "PHONE_NUMBER" ? b.phone_number?.replace(/[\s-]/g, "") : undefined,
    })),
    examples: Object.fromEntries(templateVariables(draft.body).map((v) => [v, (draft.examples[v] ?? "").trim()])),
  };
}

/**
 * A template's content as the API lists it (spec 075, `draft` of each row):
 * already split by the server, the one place that decides what can be edited.
 */
export type TemplateContent = {
  category: string | null;
  header_text: string | null;
  body_text: string;
  footer_text: string | null;
  buttons: Array<{ type: string; label: string; url?: string | null; phone_number?: string | null }>;
  examples: Record<string, string>;
};

const BUTTON_TYPES: ReadonlyArray<ButtonDraft["type"]> = ["QUICK_REPLY", "URL", "PHONE_NUMBER"];

/** Pure: the API's `draft` of a template → what the editor starts from, keeping its name. */
export function draftFromContent(name: string, language: string, content: TemplateContent): TemplateDraft {
  return {
    name,
    language,
    category: content.category === "MARKETING" ? "MARKETING" : "UTILITY",
    header: content.header_text ?? "",
    body: content.body_text ?? "",
    footer: content.footer_text ?? "",
    buttons: (content.buttons ?? [])
      .filter((b): b is typeof b & { type: ButtonDraft["type"] } => BUTTON_TYPES.includes(b.type as ButtonDraft["type"]))
      .map((b) => ({
        type: b.type,
        label: b.label ?? "",
        ...(b.type === "URL" ? { url: b.url ?? "" } : {}),
        ...(b.type === "PHONE_NUMBER" ? { phone_number: b.phone_number ?? "" } : {}),
      })),
    examples: { ...(content.examples ?? {}) },
  };
}

/**
 * The variables of a template Auphere sends by its name (spec 075, 4.1):
 * `exact` — exactly these (Reservas); `subset_keep` — none outside these, and
 * none the current version carries may go (cobros).
 */
export type SystemVariables = { mode: "exact" | "subset_keep"; variables: string[] };

/** Pure (4.2, 4.3): what the body lacks and what it carries that Auphere does not send. */
export function systemVariableIssues(
  body: string,
  system: SystemVariables,
  currentBody: string,
): { missing: string[]; extra: string[] } {
  const present = templateVariables(body);
  const extra = present.filter((v) => !system.variables.includes(v));
  // subset_keep protects what the current version carries **and** Auphere sends, as the API does.
  const required =
    system.mode === "exact" ? system.variables : templateVariables(currentBody).filter((v) => system.variables.includes(v));
  return { missing: required.filter((v) => !present.includes(v)), extra };
}

/**
 * Pure (spec 075, 1.1, 3.1, 3.2): whether to offer «Editar». The API decides
 * (`edit_blocker`, R3); without its draft and fingerprint there is nothing to
 * edit from, so an API that does not send them yet opens no editor.
 */
export function canEditTemplate(row: { edit_blocker?: string | null; draft?: unknown; version?: string | null }): boolean {
  return !row.edit_blocker && !!row.draft && !!row.version;
}

/** Why the server asks to confirm before sending to Meta (2.2, 5.1). */
export type TemplateConfirmReason = { kind: string; count?: number };

/** What the API answered when an edit was not saved, read the same way in both screens (9.3). */
export type TemplateEditFailure =
  | { kind: "template_changed" }
  | { kind: "template_not_found" }
  | { kind: "not_editable"; blocker: string | null }
  | { kind: "confirmation_required"; reasons: TemplateConfirmReason[] }
  | { kind: "category_locked" }
  | { kind: "system_variables"; missing: string[]; extra: string[] }
  | { kind: "missing_examples"; variables: string[] }
  | { kind: "meta_rejected"; metaCode: number | null; metaSubcode: number | null; userMessage: string | null }
  | { kind: "whatsapp_not_connected" }
  | { kind: "forbidden" }
  | { kind: "unknown" };

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const integer = (v: unknown): number | null => (typeof v === "number" && Number.isInteger(v) ? v : null);

/**
 * Pure: the closed code of a failed edit (contract `template-edit.md`) and the
 * fields it carried → what the screen says. Meta's own text (`user_message`)
 * is passed through as data, to be shown, never logged (8.5).
 */
export function templateEditFailure(
  code: string | null | undefined,
  info: Record<string, unknown> | null | undefined,
  status?: number,
): TemplateEditFailure {
  const data = info ?? {};
  switch (code) {
    case "template_changed":
    case "template_not_found":
    case "category_locked":
    case "whatsapp_not_connected":
      return { kind: code };
    case "not_editable":
      return { kind: "not_editable", blocker: typeof data.blocker === "string" ? data.blocker : null };
    case "confirmation_required": {
      const reasons = Array.isArray(data.reasons) ? data.reasons : [];
      return {
        kind: "confirmation_required",
        reasons: reasons
          .filter((r): r is Record<string, unknown> => !!r && typeof r === "object" && typeof (r as { kind?: unknown }).kind === "string")
          .map((r) => (integer(r.count) === null ? { kind: r.kind as string } : { kind: r.kind as string, count: integer(r.count) as number })),
      };
    }
    case "system_variables":
      return { kind: "system_variables", missing: strings(data.missing), extra: strings(data.extra) };
    case "missing_examples":
      return { kind: "missing_examples", variables: strings(data.variables) };
    case "meta_rejected":
      return {
        kind: "meta_rejected",
        metaCode: integer(data.meta_code),
        metaSubcode: integer(data.meta_subcode),
        userMessage: typeof data.user_message === "string" && data.user_message.trim() ? data.user_message : null,
      };
    default:
      return status === 403 ? { kind: "forbidden" } : { kind: "unknown" };
  }
}
