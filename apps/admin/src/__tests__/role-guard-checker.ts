/**
 * The checker behind `server-actions-require-operator.test.ts` (spec 078,
 * requisitos 1 y 3; spec 079, requisitos 2 y 4). It reads the code and lists
 * every place that does not start with the guard of its surface, called with a
 * permission literal that exists in the matrix:
 *
 * - each exported function of a `"use server"` file → `requireOperator("…")`,
 *   or a call to a function of the same file that gets the permission literal
 *   as its first argument and starts with `requireOperator(<that parameter>)`;
 * - each server page and layout of `app/(dashboard)` (and its
 *   `generateMetadata` when it reads the API) → `requirePageOperator("…")`;
 * - each exported handler of any `route.ts` under `app` → `routeOperator("…")`,
 *   followed by returning its refusal.
 *
 * «First» and not «somewhere»: a guard after a write, inside an `if`, without
 * `await` or inside a `try` that swallows the redirect protects nothing. It
 * sweeps; it never holds a list of known places (constitution §I). It lives
 * outside the test so spec 079's T024 can run it against bad examples.
 */
import fs from "node:fs";
import path from "node:path";

import ts from "typescript";

import { PERMISSIONS } from "@/lib/permissions";

export type Surface = "action" | "page" | "route";

export const GUARD: Record<Surface, string> = {
  action: "requireOperator",
  page: "requirePageOperator",
  route: "routeOperator",
};

const KNOWN = new Set<string>(Object.keys(PERMISSIONS));
const CODE = /\.(tsx?|jsx?|mjs|cjs)$/;
const TEST = /\.(test|spec)\.[cm]?[jt]sx?$/;
const HANDLERS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]);

export function sourceFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "__tests__") return [];
      return sourceFiles(full);
    }
    return CODE.test(entry.name) && !TEST.test(entry.name) ? [full] : [];
  });
}

export function parse(file: string): ts.SourceFile {
  const text = fs.readFileSync(file, "utf8");
  const kind = /\.[cm]?jsx?$/.test(file) ? ts.ScriptKind.JSX : ts.ScriptKind.TSX;
  return ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
}

export function directive(sf: ts.SourceFile): string | null {
  for (const statement of sf.statements) {
    if (!ts.isExpressionStatement(statement) || !ts.isStringLiteral(statement.expression)) return null;
    if (statement.expression.text === "use server" || statement.expression.text === "use client") {
      return statement.expression.text;
    }
  }
  return null;
}

function hasModifier(node: ts.Node, kind: ts.SyntaxKind): boolean {
  return ts.canHaveModifiers(node) && (ts.getModifiers(node) ?? []).some((m) => m.kind === kind);
}

export type Fn = { name: string; node: ts.FunctionLikeDeclaration; exported: boolean; isDefault: boolean };

export function topLevelFunctions(sf: ts.SourceFile): Fn[] {
  const out: Fn[] = [];
  for (const statement of sf.statements) {
    if (ts.isFunctionDeclaration(statement) && statement.body) {
      out.push({
        name: statement.name?.text ?? "default",
        node: statement,
        exported: hasModifier(statement, ts.SyntaxKind.ExportKeyword),
        isDefault: hasModifier(statement, ts.SyntaxKind.DefaultKeyword),
      });
    }
    if (ts.isVariableStatement(statement)) {
      for (const decl of statement.declarationList.declarations) {
        const init = decl.initializer;
        if (ts.isIdentifier(decl.name) && init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init))) {
          out.push({
            name: decl.name.text,
            node: init,
            exported: hasModifier(statement, ts.SyntaxKind.ExportKeyword),
            isDefault: false,
          });
        }
      }
    }
  }
  return out;
}

function statementsOf(fn: ts.FunctionLikeDeclaration): ts.Statement[] {
  return fn.body && ts.isBlock(fn.body) ? [...fn.body.statements] : [];
}

/** `const { id } = await params;`: reading the route's parameters talks to nobody. */
function isRouteParams(statement: ts.Statement): boolean {
  if (!ts.isVariableStatement(statement)) return false;
  const init = statement.declarationList.declarations[0]?.initializer;
  return !!init && ts.isAwaitExpression(init) && /^(props\.)?(params|searchParams)$/.test(init.expression.getText());
}

type Verdict = { ok: true } | { ok: false; why: string };
const OK: Verdict = { ok: true };
const bad = (why: string): Verdict => ({ ok: false, why });

/** The guard's argument: a single string literal that is a permission of the matrix. */
function literalPermission(call: ts.CallExpression): Verdict {
  if (call.arguments.length !== 1) return bad("sin permiso");
  const [arg] = call.arguments;
  if (!arg || !ts.isStringLiteral(arg)) return bad("el permiso no es un literal");
  return KNOWN.has(arg.text) ? OK : bad(`permiso desconocido «${arg.text}»`);
}

const callTo = (node: ts.Node | undefined, name: string): node is ts.CallExpression =>
  !!node && ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === name;

/** The awaited expression of `await x` or `const v = await x`, if the statement is one of those. */
function awaitedOf(statement: ts.Statement | undefined): ts.Expression | null {
  if (!statement) return null;
  let expr: ts.Expression | undefined;
  if (ts.isExpressionStatement(statement)) expr = statement.expression;
  if (ts.isVariableStatement(statement) && statement.declarationList.declarations.length === 1) {
    expr = statement.declarationList.declarations[0]?.initializer;
  }
  return expr && ts.isAwaitExpression(expr) ? expr.expression : null;
}

/** `await guard("p")`, or for pages `await Promise.all([guard("p"), …])`. */
function guardStatement(statement: ts.Statement | undefined, guard: string, allowAll: boolean): Verdict | null {
  const awaited = awaitedOf(statement);
  if (!awaited) return null;
  if (callTo(awaited, guard)) return literalPermission(awaited);
  if (
    allowAll &&
    ts.isCallExpression(awaited) &&
    awaited.expression.getText() === "Promise.all" &&
    awaited.arguments[0] &&
    ts.isArrayLiteralExpression(awaited.arguments[0])
  ) {
    const inner = awaited.arguments[0].elements.find((e) => callTo(e, guard));
    return inner && ts.isCallExpression(inner) ? literalPermission(inner) : null;
  }
  return null;
}

/**
 * `return helper("p", …)` or `const r = await helper("p", …)`, where `helper`
 * is a function of the same file whose first statement is
 * `await requireOperator(<its first parameter>)`.
 */
function guardedHelperCall(statement: ts.Statement, local: Map<string, ts.FunctionLikeDeclaration>): Verdict | null {
  let expr: ts.Expression | undefined;
  if (ts.isReturnStatement(statement)) expr = statement.expression;
  if (ts.isVariableStatement(statement) && statement.declarationList.declarations.length === 1) {
    expr = statement.declarationList.declarations[0]?.initializer;
  }
  if (expr && ts.isAwaitExpression(expr)) expr = expr.expression;
  if (!expr || !ts.isCallExpression(expr) || !ts.isIdentifier(expr.expression)) return null;
  const helper = local.get(expr.expression.text);
  if (!helper) return null;
  const param = helper.parameters[0]?.name;
  const awaited = awaitedOf(statementsOf(helper)[0]);
  const forwards =
    !!param &&
    ts.isIdentifier(param) &&
    callTo(awaited ?? undefined, GUARD.action) &&
    (awaited as ts.CallExpression).arguments.length === 1 &&
    (awaited as ts.CallExpression).arguments[0]?.getText() === param.text;
  if (!forwards) return bad(`«${expr.expression.text}» no empieza por ${GUARD.action}(<su primer parámetro>)`);
  const [first] = expr.arguments;
  if (!first || !ts.isStringLiteral(first)) return bad(`«${expr.expression.text}» no recibe el permiso como literal`);
  return KNOWN.has(first.text) ? OK : bad(`permiso desconocido «${first.text}»`);
}

/** `if (x instanceof Response) return x;` right after `const x = await routeOperator(…)`. */
function returnsRefusal(guard: ts.Statement, next: ts.Statement | undefined): boolean {
  if (!ts.isVariableStatement(guard) || !next || !ts.isIfStatement(next)) return false;
  const name = guard.declarationList.declarations[0]?.name;
  const cond = next.expression;
  const then = ts.isBlock(next.thenStatement) ? next.thenStatement.statements[0] : next.thenStatement;
  return (
    !!name &&
    ts.isIdentifier(name) &&
    ts.isBinaryExpression(cond) &&
    cond.operatorToken.kind === ts.SyntaxKind.InstanceOfKeyword &&
    cond.left.getText() === name.text &&
    cond.right.getText() === "Response" &&
    !!then &&
    ts.isReturnStatement(then) &&
    then.expression?.getText() === name.text
  );
}

function verdict(fn: ts.FunctionLikeDeclaration, local: Map<string, ts.FunctionLikeDeclaration>, surface: Surface): Verdict {
  const statements = statementsOf(fn);
  if (surface === "page") while (statements[0] && isRouteParams(statements[0])) statements.shift();
  const [first, second] = statements;
  if (!first) return bad(`no empieza por ${GUARD[surface]}`);
  const guarded = guardStatement(first, GUARD[surface], surface === "page");
  if (guarded) {
    if (!guarded.ok || surface !== "route") return guarded;
    return returnsRefusal(first, second) ? OK : bad("no devuelve el rechazo de routeOperator");
  }
  if (surface === "action") {
    const viaHelper = guardedHelperCall(first, local);
    if (viaHelper) return viaHelper;
  }
  return bad(`no empieza por ${GUARD[surface]}`);
}

const describeIn = (root: string, file: string) => path.relative(root, file).split(path.sep).join("/");

/** Exports this checker cannot read as a function. Types are fine. */
function unreadableExports(sf: ts.SourceFile): string[] {
  const out: string[] = [];
  for (const statement of sf.statements) {
    if (ts.isExportAssignment(statement)) out.push("export default <expresión>");
    if (ts.isExportDeclaration(statement) && !statement.isTypeOnly) out.push("export { … }");
    if (ts.isVariableStatement(statement) && hasModifier(statement, ts.SyntaxKind.ExportKeyword)) {
      for (const decl of statement.declarationList.declarations) {
        const init = decl.initializer;
        if (!init || !(ts.isArrowFunction(init) || ts.isFunctionExpression(init))) out.push(decl.name.getText(sf));
      }
    }
  }
  return out;
}

export type Report = { checked: number; violations: string[] };

/** Every exported function of every `"use server"` file under `root`. */
export function checkActions(root: string, exempt: ReadonlySet<string> = new Set()): Report {
  const files = sourceFiles(root)
    .map((file) => ({ file, sf: parse(file) }))
    .filter(({ sf }) => directive(sf) === "use server");
  let checked = 0;
  const violations = files.flatMap(({ file, sf }) => {
    const fns = topLevelFunctions(sf);
    const local = new Map(fns.map((f) => [f.name, f.node]));
    const unreadable = unreadableExports(sf).map((e) => `${describeIn(root, file)}::${e}: exportación que la prueba no sabe leer`);
    const found = fns
      .filter((f) => f.exported && !exempt.has(`${describeIn(root, file)}::${f.name}`))
      .flatMap((f) => {
        checked += 1;
        const v = verdict(f.node, local, "action");
        return v.ok ? [] : [`${describeIn(root, file)}::${f.name}: ${v.why}`];
      });
    return [...unreadable, ...found];
  });
  return { checked, violations };
}

/** Every server page and layout under `root` (an `app/(dashboard)` folder). */
export function checkPages(root: string): Report {
  const segments = sourceFiles(root)
    .filter((file) => /^(page|layout)\.[cm]?[jt]sx?$/.test(path.basename(file)))
    .map((file) => ({ file, sf: parse(file) }))
    .filter(({ sf }) => directive(sf) !== "use client");
  const violations = segments.flatMap(({ file, sf }) => {
    const fns = topLevelFunctions(sf);
    const local = new Map(fns.map((f) => [f.name, f.node]));
    const out: string[] = [];
    const main = fns.find((f) => f.isDefault);
    if (!main) out.push(`${describeIn(root, file)}: sin función por defecto que la prueba sepa leer`);
    else {
      const v = verdict(main.node, local, "page");
      if (!v.ok) out.push(`${describeIn(root, file)}::default: ${v.why}`);
    }
    const meta = fns.find((f) => f.name === "generateMetadata");
    if (meta && /backend|qaapi|fetch\(/i.test(meta.node.getText(sf))) {
      const v = verdict(meta.node, local, "page");
      if (!v.ok) out.push(`${describeIn(root, file)}::generateMetadata: ${v.why}`);
    }
    return out;
  });
  return { checked: segments.length, violations };
}

/** Every exported HTTP handler of every `route.ts` under `root` (the whole `app` folder). */
export function checkRoutes(root: string): Report {
  const routes = sourceFiles(root)
    .filter((file) => /^route\.[cm]?[jt]sx?$/.test(path.basename(file)))
    .map((file) => ({ file, sf: parse(file) }));
  let checked = 0;
  const violations = routes.flatMap(({ file, sf }) => {
    const fns = topLevelFunctions(sf);
    const local = new Map(fns.map((f) => [f.name, f.node]));
    return fns
      .filter((f) => f.exported && HANDLERS.has(f.name))
      .flatMap((f) => {
        checked += 1;
        const v = verdict(f.node, local, "route");
        return v.ok ? [] : [`${describeIn(root, file)}::${f.name}: ${v.why}`];
      });
  });
  return { checked, violations };
}

/** `"use server"` inside a function: an inline action this checker cannot see. */
export function hasInlineUseServer(sf: ts.SourceFile): boolean {
  let found = false;
  const visit = (node: ts.Node): void => {
    if (found) return;
    if (ts.isStringLiteral(node) && node.text === "use server" && node.parent !== undefined) {
      const holder = node.parent.parent;
      if (holder && holder !== sf && !ts.isSourceFile(holder)) {
        found = true;
        return;
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return found;
}
