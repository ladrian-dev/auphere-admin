# Bug Verification: el panel enseña un enlace que no abre y calla el fallo de envío

- **Slug**: enlace-de-invitacion-que-no-abre
- **Tested**: 2026-11-03
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

Las dos mitades están comprobadas por separado: la API devuelve el enlace absoluto, y los componentes reales lo enseñan y mantienen el aviso en Next de verdad. **Falta verlas juntas**: el panel con sesión contra la API. Por eso es `partial` y no `verified`.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción, API | `pytest tests/unit/test_admin_client_members.py` y archivos relacionados | pass | Dentro de la tanda de 1706 pasadas |
| Reproducción, panel | `vitest` de `access/__tests__` | pass | 13 casos nuevos |
| Panel completo | `pnpm test` en `apps/admin` | pass | 60 archivos, 385 pruebas |
| Tipos | `pnpm typecheck` | pass | |
| Lint | `pnpm lint` | pass | `--max-warnings 0` |
| Build | `pnpm build` en `apps/admin` | pass | Compila, con la ruta `/tenants/[id]/access` |
| Lint de la API | `./scripts/verify.sh lint` | pass | «Todo verde» |
| Navegador real, con arnés | Copia exacta de los componentes en una ruta temporal, con acciones de servidor simuladas que llaman a `revalidatePath`, sobre `next dev`. Ya retirada | pass | Ver abajo |
| Panel con sesión contra la API | | not-run | Exige iniciar sesión en el panel, y nadie lo pidió expresamente |
| Lector de pantalla real | | not-run | `role` y orden comprobados en el DOM, no con VoiceOver |

**Lo visto en el navegador:**

- Con el envío fallido, la alerta y el enlace siguen ahí tras `revalidatePath`, que repintó la tabla, y 8 segundos después, con 0 toasts.
- `location.href` no cambia y no lleva el token. La alerta tampoco contiene el token.
- Reenviar deja un solo enlace, el nuevo. Revocar retira su aviso y deja el de la otra persona.
- A 360 px, con una dirección de 100 caracteres: `scrollWidth == clientWidth` y ningún aviso se desborda.
- Foco por teclado: copiar y cerrar con `:focus-visible` y contorno de 2 px. Objetivos de 102×36 y 24×24 px. Al enfocar el campo se selecciona el enlace.
- axe-core 4.13 (WCAG 2.0, 2.1 y 2.2 A y AA): 0 violaciones en claro y en oscuro.
- El portapapeles estaba denegado en ese panel, así que allí se vio el camino de fallo («No se pudo copiar…»). La copia correcta solo está probada en `vitest`.

## Output Excerpts

```
Test Files  60 passed (60)
     Tests  385 passed (385)
{ "alerts": 1, "links": ["https://console.local.test/invite/tok-8420oei1j59-l7fw9zoz3x"], "rows": 1 }
```

## Residual Risks

- La unión de las dos mitades solo está cubierta por el tipo de `backend.ts`: `call<T>` devuelve el JSON tal cual.
- Recargar pierde el aviso, y otro operador no ve el fallo. El texto del aviso lo dice.
- `NEXUS_CONSOLE_BASE_URL` de cada entorno no se ha mirado: producción se niega a arrancar con `localhost`, y staging lo fija en su configuración.
- Contraste del anillo de foco: viene de los tokens y no se ha medido su relación 3:1.

## Recommendation

Antes de cerrar, una comprobación de un minuto en local o en staging: en la pestaña Acceso de un cliente, invitar a una dirección de prueba y abrir el enlace que enseña el aviso. Para ver la alerta, el entorno tiene que no poder enviar: en local, `NEXUS_EMAIL_DELIVERY=resend` sin clave.
