---
allowed-tools: Read, Grep, Glob, Skill, mcp__playwright__*
description: Audit a component or screen against Scott Hurff's 5 UI states (loading, empty, error, partial, ideal) plus edge cases (offline, auth expired, long text, 200% zoom). Refuses to mark done if only the ideal state exists.
argument-hint: "<component file or route> e.g. src/components/tenants/TenantList.tsx or /tenants"
---

# UI States Audit — $ARGUMENTS

Target: `$ARGUMENTS`

## Step 1 — Invoke the `ui-states-checklist` skill
Load the `ui-states-checklist` skill from user skills.

## Step 2 — Read the target

If it is a file path, read it and analyze the JSX/TSX for state handling:
- Look for: `isLoading`, `isError`, `isEmpty`, `<Suspense>`, `error.tsx`, `loading.tsx`, `EmptyState`, `useOptimistic`, `useFormStatus`.
- Inventory which of the 5 states is implemented and which is missing.

If it is a route, also use Playwright MCP to render each state in the live app:
- Loading: throttle network, capture screenshot.
- Empty: navigate to a tenant with no data (or mock empty response).
- Error: kill the API or intercept the request to return 500.
- Partial: paginated list mid-scroll, or a slow stream.
- Ideal: realistic content with long German strings (32+ chars).

## Step 3 — Cross-cutting edge cases

For interactive components, also verify:
- Offline behavior (queue mutations or show banner).
- Auth expiry handling (redirect with deep-link preserved).
- Keyboard-only flow.
- 200% browser zoom (no layout break).
- Form sub-states: pristine / dirty / touched / submitting / submitted / error.

## Step 4 — Output

Checklist with ✅ / ❌ / ⚠️ per state, linked to `file:line` where each state is (or is not) implemented. End with:
- **Verdict**: SHIP / NEEDS WORK / NOT STARTED
- Count of 🔴 blockers
- Top 3 missing states ordered by user impact
