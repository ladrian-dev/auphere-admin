# Bug Fix: las casillas de Herramientas y Ajustes no tienen nombre accesible en el HTML del servidor

- **Slug**: casillas-sin-nombre-en-el-html-del-servidor
- **Fixed**: 2026-09-23
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

La etiqueta se enlaza ahora en el servidor: `FormLabel` expone un `id` estable y
`FormControl` lo pasa como `aria-labelledby` al control; las casillas sueltas de
Herramientas y de los disparadores de escalado llevan `aria-labelledby` a una
`Label` con `id`. El `<span role="checkbox">` de Base UI nace con nombre, en vez de
recibirlo tras hidratar.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `packages/ui/src/components/form.tsx` | modificado | `formLabelId` en `useFormField`; `FormLabel id`; `FormControl aria-labelledby` |
| `packages/ui/src/components/__tests__/form-ssr-name.test.tsx` | añadido | SSR con `renderToStaticMarkup` |
| `apps/console/src/components/agent-tools/tools-catalog.tsx` | modificado | `Label id` + `Checkbox aria-labelledby`, con el porqué al lado |
| `apps/console/src/components/agent-tools/agent-settings-form.tsx` | modificado | ídem en los cuatro disparadores; las otras dos casillas van por `FormControl` |

## Diff Highlights

```tsx
// form.tsx
formLabelId: `${id}-form-item-label`,
…
<Label … id={formLabelId} htmlFor={formItemId} {...props} />
…
"aria-labelledby": formLabelId,
```

```tsx
// tools-catalog.tsx
<Checkbox id={id} aria-labelledby={`${id}-label`} … />
<Label id={`${id}-label`} htmlFor={id} …>
```

## Tests Added or Updated

- `form-ssr-name.test.tsx`: el HTML estático de un `FormControl` con `Checkbox`
  contiene `aria-labelledby` en el `span role="checkbox"` y el `id` referenciado.

## Local Verification

```
NODE_OPTIONS=--experimental-require-module pnpm --filter @nexus/ui exec vitest run src/components/__tests__/form-ssr-name.test.tsx   # 1 passed
pnpm --filter @nexus/ui exec eslint … && tsc --noEmit -p .                                                                          # limpios
pnpm --filter console exec tsc --noEmit && eslint tools-catalog.tsx agent-settings-form.tsx                                          # limpios
fetch('/clients/panaderia-la-espiga/tools') → 46 de 46 span[role=checkbox] con aria-labelledby (antes 0 de 46); /agent/settings → 6 de 6
pnpm exec playwright test e2e/a11y.spec.ts -g "agent/settings|view /tools"   # ver resultado abajo
```

```
✓ [setup] authenticate as a partner owner (2.8s)
✓ CP-30 › client view /agent/settings (4.4s)
✓ CP-30 › client view /tools (6.9s)
3 passed (18.4s)
```

## Deviations from Assessment

Ninguna.

## Follow-ups

- Cualquier control de Base UI usado fuera de `FormControl` y sin
  `aria-labelledby` explícito tiene el mismo problema latente (`Select`,
  `Switch` si se añaden). Regla para el DS: enlazar siempre por id, nunca fiarse
  del efecto de cliente.
