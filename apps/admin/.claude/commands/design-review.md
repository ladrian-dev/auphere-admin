---
allowed-tools: Read, Grep, Glob, Bash(git diff:*), Bash(git log:*), Bash(git status:*), Task, mcp__playwright__*, mcp__chrome-devtools__*
description: Run the design-reviewer subagent on the current branch's UI changes. Outputs scored review against Anthropic's 4 criteria (Design Quality, Originality, Craft, Functionality) — must average ≥7.5 to ship.
---

# Design Review — current branch

Delegate the full review to the `design-reviewer` subagent. Do NOT review in the main context — keep the report self-contained.

## Changed files in this branch
!`git diff --name-only main...HEAD 2>/dev/null || git diff --name-only HEAD~5...HEAD`

## Diff summary
!`git diff main...HEAD --stat 2>/dev/null || git diff HEAD~5...HEAD --stat`

## Instructions to the subagent

Invoke `@design-reviewer` with this brief:

> Review the UI changes in the current branch. Affected files are listed above. Before starting, verify the dev server is running at `http://localhost:3000` — if not, ask the user to start it with `pnpm dev` from `apps/admin/`. Walk every affected route with Playwright MCP, test the 5 UI states per data-rendering component, screenshot at 360 / 768 / 1024 / 1440, run axe via Playwright. Score against the 4 Anthropic criteria. Verdict: SHIP / NEEDS WORK / DO NOT SHIP.

Pass through any additional context from the user (e.g. "focus on the tenant detail screen") that came with the `/design-review` invocation.

After the subagent returns, summarize for the user in ≤80 words: verdict + count of 🔴 / 🟡 / 🟢 + score. Then offer to open the first 🔴 in the editor.
