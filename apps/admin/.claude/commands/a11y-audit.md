---
allowed-tools: Read, Grep, Glob, Bash, Skill, mcp__playwright__*
description: Run a WCAG 2.2 AA accessibility audit on a route or component. Uses axe-core via Playwright MCP when the dev server is running; falls back to static analysis otherwise.
argument-hint: "<route or component path> e.g. /tenants/[id] or src/components/qa/QAPlayground.tsx"
---

# Accessibility Audit — $ARGUMENTS

Target: `$ARGUMENTS`

## Step 1 — Invoke the `a11y-audit` skill
Load and follow the `a11y-audit` skill from user skills. It contains the full WCAG 2.2 AA checklist including the 9 new criteria.

## Step 2 — Live audit (if a route was provided)
If `$ARGUMENTS` looks like a route (starts with `/`), use Playwright MCP:
1. Navigate to `http://localhost:3000$ARGUMENTS`.
2. Inject `axe-core` via the CDN: `https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js`.
3. Run `axe.run()`, capture violations.
4. Take screenshots at 360 / 1024 / 1440 viewports.
5. Repeat in dark mode (toggle `[data-theme="dark"]` on `<html>`).

If `$ARGUMENTS` looks like a file path, read the file and audit statically — note that static analysis cannot verify computed contrast, so flag that explicitly.

## Step 3 — Output

Per violation: severity 🔴/🟡/🟢 · WCAG criterion · file:line (when known) · user impact (NOT the fix).

End with verdict: **AA-COMPLIANT** / **PARTIAL** (count 🔴) / **NON-COMPLIANT**. Do not mark AA-COMPLIANT with any 🔴 outstanding.
