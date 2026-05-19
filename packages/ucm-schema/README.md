# `ucm-schema` — Universal Channel Message v1.0.0

Schema-versioned, channel-agnostic message format that Nexus agents emit instead of channel-native payloads. The agent emits one UCM; per-channel renderers translate it (WhatsApp, web, Instagram, …). When a channel can't render the native form, the **degradation engine** produces the closest renderable variant or falls back to plain text — never blank, never broken.

> Decision of record: [ADR-020](../../../Work/Auphere/nexus/decisions/ADR-020-qa-playground-ucm-multichannel.md)
> Plan: [features/qa-playground-mvp](../../../Work/Auphere/nexus/features/qa-playground-mvp.md), Fase 1.

## Layout

```
packages/ucm-schema/
├── fixtures/        canonical example payloads — cross-language source of truth
│   ├── valid.json
│   └── invalid.json
├── ts/              TypeScript package (Zod + JSON Schema)
│   ├── src/
│   ├── tests/       Vitest
│   └── package.json
└── py/              Python package (Pydantic v2)
    ├── src/ucm_schema/
    ├── tests/       Pytest
    └── pyproject.toml
```

## What UCM v1.0.0 covers

8 message types:

| Type | Capability key | Used for |
|---|---|---|
| `text` | `text` (+ `text.markdown`) | Plain or markdown body. |
| `quick_replies` | `interactive.buttons` | 1–10 buttons. WhatsApp caps at 3. |
| `list` | `interactive.list` | Sectioned picker. WhatsApp caps at 10 rows. |
| `cta_url` | `interactive.cta_url` | Single body + button → URL. |
| `media` | `media.image` / `video` / `document` / `audio` | URL-hosted media with caption. |
| `location` | `location` | lat/lon + name/address. |
| `flow` | `flow` | WhatsApp Flow / equivalent. |
| `composite` | (recursive) | Ordered group of child UCMs. |

Every UCM carries: `ucm_version`, `message_id`, `type`, `capabilities_required[]`, `fallback_text` (mandatory), `metadata`, `content`.

## Channels supported in v1

`web`, `whatsapp`, `instagram`, `messenger`, `voice`.

Adding a new channel = new entry in `channels/capabilities.{ts,py}` + a renderer in the consumer. Nothing else here changes.

## Public API

### TypeScript

```ts
import {
  UCM_VERSION, UCMMessageSchema,
  validate, degrade,
  CHANNELS, getChannel,
} from "@nexus/ucm-schema";

const ucm = UCMMessageSchema.parse(rawPayload);   // shape validation
const v = validate(ucm, "whatsapp");              // shape + channel-limit
const d = degrade(ucm, "voice");                  // graceful fallback
```

Both `validate` and `degrade` also accept a `ChannelProfile` directly — useful for tests or experimental channels not yet in `CHANNELS`.

### Python

```python
from ucm_schema import UCM_VERSION, parse_ucm, validate, degrade, get_channel

ucm = parse_ucm(raw_payload)            # → Pydantic UCMMessage
v = validate(raw_payload, "whatsapp")   # → ValidationResult
d = degrade(ucm, "voice")               # → DegradeResult
```

## Versioning

Strict semver. `ucm_version` is part of every payload. When v2 ships:
- `SUPPORTED_UCM_VERSIONS` widens to `("1.0.0", "2.0.0")`.
- Boundary code (renderers, formatter node) reads `ucm_version` and dispatches.
- Promise: support N + N−1 for at least one quarter; never remove a v1 type without v2 deprecation period.

## Cross-language contract

`fixtures/valid.json` and `fixtures/invalid.json` are the single source of truth. Both TS and Python tests load them and assert identical outcomes (accept / reject + which kind of issue). If a fixture passes in one language and not the other, the build fails — that's the contract.

## Running the tests

```bash
# TypeScript
cd packages/ucm-schema/ts
pnpm install
pnpm test:coverage         # vitest with v8 coverage, thresholds enforced

# Python
cd packages/ucm-schema/py
uv venv --python 3.11 && uv pip install -e ".[test]"
.venv/bin/pytest --cov     # pytest + coverage, fail_under=90 enforced
```

Current coverage (2026-05-19): TS 97.18% lines · Python 95.12% lines.

## Status

`ucm-schema@1.0.0` — internal release, used by Nexus monorepo only. Not published to public npm/PyPI. Frozen API: any breaking change requires a major bump and an ADR.

Next: Fase 2 — wire `ucm_formatter` as the final node of a piloto agent's graph, with shadow validation against the current WhatsApp output for 7 days before promoting to source of truth.
