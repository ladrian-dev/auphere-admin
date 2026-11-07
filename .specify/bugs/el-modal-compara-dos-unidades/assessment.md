# Bug Assessment: el modal compara millonésimas con cien milésimas

- **Slug**: el-modal-compara-dos-unidades
- **Created**: 2026-11-05
- **Source**: Encontrado el 2026-11-05, al explicar a Luis el «tope de 5 o 50».
- **Verdict**: valid
- **Severity**: medium

## Symptom

`doesNotFit` comparaba la estimación (millonésimas de dólar) con lo que queda de la partida (cien milésimas). Lo que quedaba parecía 10 veces menos: con 50 USD de tope decía que quedaban 5, y una pasada de 6 USD parecía no caber. Vino en `6169814a`, del 2026-11-04.

## Reproduction

`apps/console/src/components/builder/__tests__/run-estimate.test.tsx`.

## Root cause

Dos unidades con el mismo nombre, `amount_micros`, y la cuenta hecha en la consola. El tope nunca fue de 5: `5_000_000` en cien milésimas son 50 (`test_usage_lines.py`).
