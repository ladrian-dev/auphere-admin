# Bug Verification: el chat de prueba y las pruebas del agente esconden que el modelo no respondió

- **Slug**: el-probador-tapa-los-fallos-del-modelo
- **Tested**: 2026-11-03
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

Con el proveedor de verdad, el proxy obligatorio y un partner sin clave, la condición de
staging, el trabajo termina `failed/model_unavailable`, la prueba es «No se pudo probar»
y el chat dice que el modelo no respondió. En un navegador se ha visto contra la API
simulada. Es `partial` porque **no se ha visto en staging**: la rama no está desplegada.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Pruebas nuevas, antes | `pytest tests/integration/builder/test_model_failures_are_not_agent_failures.py` | fail | 11 de 12 en rojo; el `KeyError: 'failure'` del chat, entre ellos. La que pasaba fija que un fallo de verdad sigue siendo fallo |
| Consola, antes | `vitest run` de chat, lista, barra y modelo | fail | 8 failed, 52 passed |
| Contrato con Terraform, antes | `pytest apps/worker/tests/unit/test_platform_alarms_contract.py` | fail | `simulated_model_failure_burst` sin alarma |
| Reproducción de staging, sin la detección | Mutación: `run_turn` sin `failure_of_turn` y `converse` sin capturar el modelo del cliente simulado | fail | `('done', None) == ('failed', 'model_unavailable')`: el síntoma de staging. La prueba se escribió después del arreglo, así que su rojo sale de aquí y no del código anterior |
| Reproducción de staging | `test_the_case_of_staging_a_partner_without_a_key_in_the_proxy` | pass | Parte de las 13 de abajo |
| Pruebas nuevas, después | El mismo archivo | pass | 13 passed |
| Regresión de la API | 22 archivos de lo tocado, con `tests/isolation/test_console_scope.py` | pass | 1731 passed en 741 s, antes de añadir la reproducción de staging |
| Migración | `tests/integration/test_migration_reversibility.py` | pass | Baja a `0115` y vuelve a `head`, con `0216` |
| Worker | `test_platform_watcher`, `test_platform_alarms_contract`, `test_simulation_failures`, `test_suite_passes_end_together`, `test_agent_tests_multiturn` | pass | 48 passed |
| Consola, después | `vitest run src/components/builder src/i18n "src/app/(console)/clients/[ref]/agents"` | pass | 46 archivos, 496 pruebas, con axe en el chat y en la lista |
| Tipos y lint de la consola | `tsc --noEmit -p tsconfig.json`, `eslint --max-warnings 0` de lo tocado | pass | |
| Lint | `./scripts/verify.sh lint` | pass | «Todo verde.» |
| Consola, los pasos de la tubería | `pnpm check:no-admin-token`, `typecheck`, `lint`, `test`; `pnpm build` con las variables de `ci.yml` | pass | 228 archivos, 1874 pruebas. Instalación propia con `pnpm install --frozen-lockfile` |
| E2E en Chromium | `playwright test -c e2e/agent-quality.config.ts e2e/agent-model-failures.e2e.ts` | pass | 4 passed. Antes del arreglo del teclado, 1 failed con `scrollable-region-focusable` |
| Auditoría de UI | Medida en el DOM real con un spec temporal, ya borrado | pass | Ver abajo. Encontró 3 🔴, ya arreglados |
| Staging | | not-run | Sin desplegar |
| Suites completas de Python | | not-run | Se corrió lo tocado, como se pidió |

Las pruebas unitarias de `failures.py` y las de la alerta en `test_platform_watcher` se
escribieron junto al código: no se vieron en rojo por separado.

## Auditoría de UI

`agent-playground.tsx`, `test-list.tsx`, `tests-box.tsx` y `publish-bar.tsx`, con los datos de
fallo.

| Comprobación | Resultado |
|---|---|
| axe (WCAG 2.2 AA) en las cuatro piezas, en claro y en oscuro | 0 violaciones, también con la conversación desbordada a 360 px |
| Contraste del texto, del color calculado | Aviso del chat y burbujas 14,25 y 9,79; lista 5,91 y 6,49; tarjeta 7,07 y 7,04; barra 7,07 y 6,97 (claro y oscuro) |
| Anillo de foco de la conversación | 2 px; 4,95:1 y 7,78:1. Se llega con Tab y las flechas desplazan |
| Sin desbordar a 320, 360, 414, 768, 1024, 1280, 1440 y 1920 px | Las cuatro piezas |
| 200 %, como viewport de 640×450 | Sin desbordar |
| Texto largo: palabra de 34 letras y token de 100 sin espacios donde va texto de personas | Sin desbordar ni recortar |
| Espaciado de texto (1.4.12) en el aviso del chat, a 360 px | Sin desbordar |
| Zonas de pulsación de 24×24 | Sin ninguna por debajo |
| Tokens: hex, `style={{}}`, paletas por defecto | Ninguno |

**Valores fuera de escala que siguen, de antes:** `h-[300px]`, `max-w-[82%]`, `max-w-[94%]` (el aviso
nuevo usa este último, como sus vecinos).

**No se ha visto:**
- Con la API de verdad ni con una sesión real: la cookie la acepta la API simulada.
- Con un lector de pantalla, Safari, Firefox o un teléfono.
- El zoom real del navegador: se aproxima con el viewport.
- En el navegador, los textos de `no_model` y `empty_response` ni la vista de solo lectura: están en pruebas de componente.

**Visto y sin tocar:** el aviso «Pruebas terminadas.» tapa un momento la barra si se guarda justo
después de ejecutar. Y `e2e/agent-quality.e2e.ts` falla en sus 4 pruebas, en su `open()`: busca
«Recepción» como `h2`, y la pantalla la pinta como `h1`.

## Output Excerpts

```
1731 passed, 5 warnings in 741.58s (0:12:21)
13 passed, 1 warning in 57.05s
Test Files  46 passed (46)
     Tests  496 passed (496)
Todo verde. La tubería debería pasar.
```

## Residual Risks

- La alarma de CloudWatch está sin aplicar: hasta entonces la alerta solo se registra.
- Los textos de `why_untested` llegan en español también con la consola en inglés, como `why_failed`.
- Desde hoy staging va directo al proveedor (ADR-036): el «missing partner virtual key» ya no es el caso de allí, y la prueba lo fuerza con el proxy. El fallo que se ve en staging será otro, y pasa por el mismo camino.

## Recommendation

Mantener abierto hasta verlo en staging: con el modelo caído o mal configurado para un
cliente, el chat debe enseñar el aviso y «Ejecutar todas» debe decir que no se pudo probar.
