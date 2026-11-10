import { readFileSync } from "node:fs";
import { join } from "node:path";

import ts from "typescript";

import { BANNER, emit } from "./_write.mts";

/**
 * Spec 031, D16: the app says what the console says. The vocabulary of the
 * Consola Lite comes from the console's own message files, by a closed list of
 * prefixes; the app's own words (tabs, sign-in, settings) live in
 * `src/i18n/app.{es,en}.ts`. «Tomar el control» is one sentence in both.
 */
const PREFIXES = [
  "inbox.",
  "lite.",
  "ui.",
  // The Panel's trend and chart words, shared with the partner's home.
  "hu.home.kpi.",
  "hu.home.chart.title",
  "hu.usage.spend.",
  "common.error.backend",
  // Spec 047 (50.1, 25.5): the agents' and channels' states, pausing, and the
  // Negocio sections — the same words the partner's console says.
  "clients.v2.agent.",
  "clients.v2.pause.",
  "builder.channel.state.",
  "builder.channel.problem.",
  "builder.life.action.pause",
  "builder.life.action.resume",
  "builder.life.pause.",
  "builder.life.paused",
  "builder.life.resumed",
  "business.hours.",
  "business.special.",
  "business.services.",
  "business.locations.",
  "business.history.",
  "business.prov.",
  "business.section.",
  "panel.bag.days",
  "panel.bag.empty",
  "panel.bag.noEstimate",
] as const;
const root = join(import.meta.dirname, "..");
const i18n = join(root, "../console/src/i18n");
const SOURCES = [
  "messages.ts",
  "lanes/inbox.ts",
  "lanes/lite.ts",
  "lanes/home-usage.ts",
  "lanes/business.ts",
  "lanes/builder-channels.ts",
  "lanes/builder-life.ts",
];

type Entry = { es: string; en: string };

function text(node: ts.Expression | undefined, file: string, key: string): string {
  if (node && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))) return node.text;
  throw new Error(`${file}: «${key}» is not a plain string`);
}

function collect(file: string, into: Map<string, Entry>): void {
  const src = ts.createSourceFile(file, readFileSync(join(i18n, file), "utf8"), ts.ScriptTarget.Latest, true);
  const visit = (node: ts.Node): void => {
    if (ts.isPropertyAssignment(node) && ts.isStringLiteral(node.name)) {
      const key = node.name.text;
      if (PREFIXES.some((p) => key.startsWith(p)) && ts.isObjectLiteralExpression(node.initializer)) {
        const props = new Map(
          node.initializer.properties
            .filter(ts.isPropertyAssignment)
            .map((p) => [p.name.getText(src), p.initializer] as const),
        );
        if (into.has(key)) throw new Error(`${file}: «${key}» is declared twice`);
        into.set(key, { es: text(props.get("es"), file, key), en: text(props.get("en"), file, key) });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(src);
}

const entries = new Map<string, Entry>();
for (const file of SOURCES) collect(file, entries);
for (const must of ["inbox.composer.takeover", "inbox.badge.waiting", "clients.v2.agent.serving", "business.hours.phrase"]) {
  if (!entries.has(must)) throw new Error(`the console no longer has «${must}»`);
}

const body = [...entries.keys()]
  .sort()
  .map((k) => `  ${JSON.stringify(k)}: { es: ${JSON.stringify(entries.get(k)!.es)}, en: ${JSON.stringify(entries.get(k)!.en)} },`)
  .join("\n");

emit(
  join(root, "src/i18n/lite.gen.ts"),
  `${BANNER}// Source: apps/console/src/i18n/{${SOURCES.join(",")}} (${PREFIXES.join(" ")}) · generator: scripts/gen-i18n.ts\n\n` +
    `export const liteMessages = {\n${body}\n} as const;\n`,
);
