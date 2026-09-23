# Iteración 1 · Ficha del cliente — evidencia

## Prototipo (T011)

- Story: `packages/ui/src/stories/prototypes/client-record.stories.tsx` (`Prototipos/Ficha de cliente`), siete estados: Falta canal · Atendiendo · Sin cupo asignado · Con borrador · Analyst · Archivado · Móvil.
- Cómo verlo: `preview_start storybook` (Node 24) → `http://localhost:6006/?path=/story/prototipos-ficha-de-cliente--con-borrador`.
- Addon a11y: sin violaciones en los siete estados (2026-09-24).
- **Aprobación del owner**: _pendiente_.

Lo que el prototipo fija: cuatro puntos con nombre y un solo botón (el del primer paso pendiente); cupo como barra o «Sin cupo asignado»; «Más» con el ciclo de vida y Eliminar solo archivado; tres grupos con nombre y selector con `optgroup` en móvil; barra de borrador bajo la navegación con «Ver diferencias» (hoja por pantalla, prompt plegado) y «Publicar»; sin permiso, la barra dice quién puede.

## Cimientos ya en la rama (Setup + Foundational)

- API: `sector`, `setup` (+`next`), `quota` en la ficha; `setup`, `quota`, `conversations_7d` en la lista; `CATEGORY_LABELS`; migración 0129.
- Tests: `tests/unit/test_console_audit_vocab_017.py`, `tests/integration/test_console_client_setup.py` (8 casos), suites `-k console` (185) e isolation `test_console_scope.py` en verde el 2026-09-24.
- `scripts/verify.sh locks` en verde (lockfiles sin cambios).
