---
allowed-tools: Read, Grep, Glob, Bash(rg:*), Bash(grep:*), Skill
description: Audit the admin codebase for design token violations — hex inline, inline styles, default shadcn palettes (slate/zinc/gray/neutral) used when semantic tokens exist, values outside the declared scale.
---

# Design Tokens Check — apps/admin

## Step 1 — Invoke the `design-tokens` skill
Load the `design-tokens` skill from user skills for the full ruleset.

## Step 2 — Confirm the source of truth

The Nexus admin's token source is `apps/admin/src/app/globals.css` (4-layered: brand → semantic → shadcn bridge → `@theme inline`). Read it and confirm the declared:
- Color tokens (semantic names: `--bg`, `--ink`, `--card`, `--bone`, `--primary`, etc.)
- Spacing scale
- Typography scale
- Radius enum

## Step 3 — Grep for violations

Run these searches under `apps/admin/src/`:

```bash
# Hex inline in JSX/TSX
rg -n --type tsx --type ts 'bg-\[#|text-\[#|border-\[#|fill-\[#|stroke-\[#' apps/admin/src/

# rgb/hsl inline
rg -n 'bg-\[rgb|text-\[rgb|bg-\[hsl|text-\[hsl' apps/admin/src/

# Inline style theming
rg -n 'style=\{\{[^}]*(color|backgroundColor|padding|margin|fontSize|borderRadius)' apps/admin/src/

# Default shadcn palettes used directly (should use semantic tokens)
rg -n '(bg|text|border|ring)-(slate|zinc|gray|neutral|stone)-[0-9]+' apps/admin/src/

# Arbitrary spacing/sizing outside the scale
rg -n '(p|m|gap|w|h|text)-\[[0-9]+(px|rem)\]' apps/admin/src/
```

## Step 4 — Output

Group findings:
- **🔴 Hex / rgb inline**: list `file:line` + offending value + the semantic token replacement.
- **🔴 Inline style theming**: list `file:line` + replacement.
- **🟡 Default palette used**: list `file:line` + the semantic token replacement.
- **🟡 Arbitrary scale values**: list `file:line` + closest scale value.
- **🟢 Tokens declared but unused** in `globals.css` (dead code).

End with:
- **Verdict**: CLEAN / PARTIAL / NON-COMPLIANT
- Count of 🔴 (zero required for CLEAN)
- Top 5 file paths with the highest violation density (priority for cleanup)
