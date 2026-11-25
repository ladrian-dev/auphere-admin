/**
 * Spec 078: el panel solo obedece a operadores activos.
 *
 * El panel habla con la API con un token de servicio, así que la API no sabe
 * quién pide cada cosa: quien decide es `requireOperator()`. Esta prueba lee el
 * código y exige que la guarda sea **lo primero** que hace:
 *
 * - cada función exportada de un archivo `"use server"` (requisito 1), sea
 *   directamente o devolviendo una función del mismo archivo que empiece por
 *   la guarda;
 * - cada página y layout de servidor de `app/(dashboard)`, y su
 *   `generateMetadata` si lee la API (requisito 3). Next no vuelve a ejecutar
 *   un layout al navegar, así que la guarda del layout raíz no basta.
 *
 * «Lo primero» y no «en algún sitio»: una guarda después de la escritura, en
 * un `if`, sin `await` o dentro de un `try` que se traga la redirección no
 * protege nada.
 */
import fs from "node:fs";
import path from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

const SRC = path.resolve(__dirname, "..");
const DASHBOARD = path.join(SRC, "app", "(dashboard)");
const GUARD = "requireOperator";

/** Abren y cierran la sesión: no pueden exigirla (requisito 1.2). */
const EXEMPT = new Set([
  "app/(auth)/login/actions.ts::loginAction",
  "app/(auth)/login/actions.ts::logoutAction",
]);

const CODE = /\.(tsx?|jsx?|mjs|cjs)$/;
const TEST = /\.(test|spec)\.[cm]?[jt]sx?$/;

function sourceFiles(dir: string, keepTests = false): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules") return [];
      if (entry.name === "__tests__" && !keepTests) return [];
      return sourceFiles(full, keepTests);
    }
    return CODE.test(entry.name) && !TEST.test(entry.name) ? [full] : [];
  });
}

const rel = (file: string) => path.relative(SRC, file).split(path.sep).join("/");

function parse(file: string): ts.SourceFile {
  const text = fs.readFileSync(file, "utf8");
  const kind = /\.[cm]?jsx?$/.test(file) ? ts.ScriptKind.JSX : ts.ScriptKind.TSX;
  return ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
}

function directive(sf: ts.SourceFile): string | null {
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

const isGuardCall = (node: ts.Node | undefined): boolean =>
  !!node && ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === GUARD;

/** `await requireOperator()` o `await Promise.all([requireOperator(), …])`. */
function isAwaitedGuard(node: ts.Expression | undefined, allowAll: boolean): boolean {
  if (!node || !ts.isAwaitExpression(node)) return false;
  if (isGuardCall(node.expression)) return true;
  if (!allowAll) return false;
  const call = node.expression;
  return (
    ts.isCallExpression(call) &&
    call.expression.getText() === "Promise.all" &&
    ts.isArrayLiteralExpression(call.arguments[0] as ts.Node) &&
    (call.arguments[0] as ts.ArrayLiteralExpression).elements.some(isGuardCall)
  );
}

/** ¿Es esta sentencia la guarda? Sola o asignada: `const op = await requireOperator();`. */
function isGuardStatement(statement: ts.Statement | undefined, allowAll: boolean): boolean {
  if (!statement) return false;
  if (ts.isExpressionStatement(statement)) return isAwaitedGuard(statement.expression, allowAll);
  if (ts.isVariableStatement(statement)) {
    const [decl] = statement.declarationList.declarations;
    return statement.declarationList.declarations.length === 1 && isAwaitedGuard(decl?.initializer, allowAll);
  }
  return false;
}

type Fn = { name: string; node: ts.FunctionLikeDeclaration; exported: boolean; isDefault: boolean };

function topLevelFunctions(sf: ts.SourceFile): Fn[] {
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

function firstStatement(fn: ts.FunctionLikeDeclaration): ts.Statement | undefined {
  return fn.body && ts.isBlock(fn.body) ? fn.body.statements[0] : undefined;
}

/** `const { id } = await params;`: leer los parámetros de la ruta no habla con nadie. */
function isRouteParams(statement: ts.Statement): boolean {
  if (!ts.isVariableStatement(statement)) return false;
  const init = statement.declarationList.declarations[0]?.initializer;
  return (
    !!init &&
    ts.isAwaitExpression(init) &&
    /^(props\.)?(params|searchParams)$/.test(init.expression.getText())
  );
}

/** Llama a una función local que empieza por la guarda: `return run(…)` o `const r = await run(…)`. */
function callsGuardedHelper(statement: ts.Statement, local: Map<string, ts.FunctionLikeDeclaration>): boolean {
  let expr: ts.Expression | undefined;
  if (ts.isReturnStatement(statement)) expr = statement.expression;
  if (ts.isVariableStatement(statement) && statement.declarationList.declarations.length === 1) {
    expr = statement.declarationList.declarations[0]?.initializer;
  }
  if (expr && ts.isAwaitExpression(expr)) expr = expr.expression;
  if (!expr || !ts.isCallExpression(expr) || !ts.isIdentifier(expr.expression)) return false;
  const helper = local.get(expr.expression.text);
  return !!helper && isGuardStatement(firstStatement(helper), false);
}

/**
 * Empieza por la guarda, o por una función local que empieza por ella. En
 * páginas (`page`) se permiten antes las lecturas de `params`/`searchParams`
 * y la guarda dentro de un `Promise.all`: una página solo lee, y si la guarda
 * redirige no se envía nada.
 */
function startsGuarded(fn: ts.FunctionLikeDeclaration, local: Map<string, ts.FunctionLikeDeclaration>, page: boolean): boolean {
  const statements = fn.body && ts.isBlock(fn.body) ? [...fn.body.statements] : [];
  while (page && statements[0] && isRouteParams(statements[0])) statements.shift();
  const first = statements[0];
  if (!first) return false;
  return isGuardStatement(first, page) || callsGuardedHelper(first, local);
}

/** Exportaciones que esta prueba no sabe leer como función. Los tipos sí valen. */
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

/** `"use server"` dentro de una función: una acción en línea que esta prueba no ve. */
function hasInlineUseServer(sf: ts.SourceFile): boolean {
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

// ---------------------------------------------------------------------------

const actionFiles = sourceFiles(SRC)
  .map((file) => ({ file, sf: parse(file) }))
  .filter(({ sf }) => directive(sf) === "use server");

describe("Server Actions del panel (spec 078, requisito 1)", () => {
  it("encuentra los archivos de acciones (la prueba no pasa en vacío)", () => {
    expect(actionFiles.length).toBeGreaterThan(20);
    const exported = actionFiles.flatMap(({ sf }) => topLevelFunctions(sf).filter((f) => f.exported));
    expect(exported.length).toBeGreaterThan(100);
  });

  it("cada función exportada empieza por la guarda", () => {
    const unguarded = actionFiles.flatMap(({ file, sf }) => {
      const fns = topLevelFunctions(sf);
      const local = new Map(fns.map((f) => [f.name, f.node]));
      return fns
        .filter((f) => f.exported)
        .map((f) => `${rel(file)}::${f.name}`)
        .filter((id) => !EXEMPT.has(id))
        .filter((id) => !startsGuarded(local.get(id.split("::")[1]!)!, local, false));
    });
    expect(unguarded).toEqual([]);
  });

  it("ningún archivo de acciones exporta algo que esta prueba no sabe leer", () => {
    expect(actionFiles.flatMap(({ file, sf }) => unreadableExports(sf).map((e) => `${rel(file)}::${e}`))).toEqual([]);
  });

  it("no hay acciones en línea (`\"use server\"` dentro de una función)", () => {
    const inline = sourceFiles(SRC).filter((file) => {
      const text = fs.readFileSync(file, "utf8");
      return text.includes("use server") && hasInlineUseServer(parse(file));
    });
    expect(inline.map(rel)).toEqual([]);
  });

  it("las excepciones siguen existiendo (si se renombran, se revisa la lista)", () => {
    const all = new Set(
      actionFiles.flatMap(({ file, sf }) => topLevelFunctions(sf).filter((f) => f.exported).map((f) => `${rel(file)}::${f.name}`)),
    );
    for (const exempt of EXEMPT) expect(all.has(exempt)).toBe(true);
  });
});

describe("Páginas y layouts del panel (spec 078, requisito 3)", () => {
  const segments = sourceFiles(DASHBOARD)
    .filter((file) => /^(page|layout)\.[cm]?[jt]sx?$/.test(path.basename(file)))
    .map((file) => ({ file, sf: parse(file) }))
    .filter(({ sf }) => directive(sf) !== "use client");

  it("encuentra las páginas (la prueba no pasa en vacío)", () => {
    expect(segments.length).toBeGreaterThan(50);
  });

  it("cada página y layout de servidor empieza por la guarda", () => {
    const unguarded = segments.flatMap(({ file, sf }) => {
      const fns = topLevelFunctions(sf);
      const local = new Map(fns.map((f) => [f.name, f.node]));
      const main = fns.find((f) => f.isDefault);
      if (!main) return [`${rel(file)}: sin función por defecto que la prueba sepa leer`];
      return startsGuarded(main.node, local, true) ? [] : [`${rel(file)}::default`];
    });
    expect(unguarded).toEqual([]);
  });

  it("generateMetadata empieza por la guarda cuando lee la API", () => {
    const unguarded = segments.flatMap(({ file, sf }) => {
      const meta = topLevelFunctions(sf).find((f) => f.name === "generateMetadata");
      if (!meta || !/backend|fetch\(/.test(meta.node.getText(sf))) return [];
      const local = new Map(topLevelFunctions(sf).map((f) => [f.name, f.node]));
      return startsGuarded(meta.node, local, true) ? [] : [`${rel(file)}::generateMetadata`];
    });
    expect(unguarded).toEqual([]);
  });
});
