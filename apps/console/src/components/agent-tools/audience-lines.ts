/**
 * Spec 024: the allowed numbers as the partner types them.
 *
 * One line per number, `+56 9 9191 9125 · Daniel, ventas`; the name after
 * the middle dot is optional, and several numbers may share a line
 * separated by commas when none of them carries a name. Pure module: the
 * form parses on submit, the API normalises again on save.
 */
import type { AudienceNumber } from "@/lib/backend/agent-tools-types";

export const NAME_SEPARATOR = "·";
const PHONE_RE = /^\+?\d{7,15}$/;

export type AudienceLineError = { line: number; text: string };
export type ParsedAudience = { numbers: AudienceNumber[]; errors: AudienceLineError[] };

/** `+56 9 9191 9125` → `+56991919125`; `null` when it could never match a sender. */
export function normalisePhone(raw: string): string | null {
  const compact = raw.replace(/[\s().-]/g, "");
  if (!PHONE_RE.test(compact)) return null;
  return compact.startsWith("+") ? compact : `+${compact}`;
}

export function parseAudienceLines(text: string): ParsedAudience {
  const numbers: AudienceNumber[] = [];
  const errors: AudienceLineError[] = [];
  const seen = new Set<string>();
  const push = (phone: string, name: string | null) => {
    if (seen.has(phone)) return;
    seen.add(phone);
    numbers.push({ phone, name });
  };
  text.split(/\r?\n/).forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) return;
    const lineNo = index + 1;
    if (line.includes(NAME_SEPARATOR)) {
      const [phonePart, ...rest] = line.split(NAME_SEPARATOR);
      const phone = normalisePhone((phonePart ?? "").trim());
      if (!phone) {
        errors.push({ line: lineNo, text: line });
        return;
      }
      const name = rest.join(NAME_SEPARATOR).trim();
      push(phone, name || null);
      return;
    }
    for (const token of line.split(",")) {
      const piece = token.trim();
      if (!piece) continue;
      const phone = normalisePhone(piece);
      if (!phone) {
        errors.push({ line: lineNo, text: piece });
        continue;
      }
      push(phone, null);
    }
  });
  return { numbers, errors };
}

export function formatAudienceLines(numbers: readonly AudienceNumber[]): string {
  return numbers.map((n) => (n.name ? `${n.phone} ${NAME_SEPARATOR} ${n.name}` : n.phone)).join("\n");
}
