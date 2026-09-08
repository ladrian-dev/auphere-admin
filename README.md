# Nexus

Auphere's agent factory — internal platform that the Auphere team operates to deliver bespoke, isolated AI agents to client businesses as a managed service.

This repo is internal. The **why** — research, decisions, ADRs, roadmap — lives in the Obsidian KB at `/Users/lmatos/Work/Auphere/nexus/`; start with `PLAN-DE-ACCION.md`.

## How work happens here

**No code lands in this repo without an approved specification behind it.**

Since 2026-09-08 this repo runs on Spec-Driven Development: specs live in `specs/NNN-<slug>/`, the nine governing principles in `.specify/memory/constitution.md`, and the full method — the flow, the gates, the EARS requirement format, and the three exceptions to the rule — in **[`docs/spec-driven-development.md`](docs/spec-driven-development.md)**. Read that before your first change.

## Quick start

```bash
docker compose up -d
curl http://localhost:8000/health
```

See `CLAUDE.md` for more.
