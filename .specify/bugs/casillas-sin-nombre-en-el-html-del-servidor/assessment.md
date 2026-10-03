# Bug Assessment: las casillas de Herramientas y Ajustes no tienen nombre accesible en el HTML del servidor

- **Slug**: casillas-sin-nombre-en-el-html-del-servidor
- **Created**: 2026-09-23
- **Source**: suite `pnpm test:e2e` (CP-30, axe) contra el stack local, 2026-09-22 y 2026-09-23; KB `nexus/AUDITORIA-UX-CONSOLA-2026-09-22.md` §5
- **Verdict**: valid
- **Severity**: high (axe lo clasifica *serious*; WCAG 4.1.2)

## Report (verbatim)

```
Error: /clients/panaderia-la-espiga/tools: serious/critical axe violations
+ "aria-toggle-field-name (serious): #base-ui-_R_18cb55esnfknebneitmlb_ | #base-ui-_R_18kb55esnfknebneitmlb_ | #base-ui-_R_18sb55esnfknebneitmlb_"
Error: /clients/panaderia-la-espiga/agent/settings: serious/critical axe violations
+ "aria-toggle-field-name (serious): #base-ui-_R_pjqatpesnfknebneitmlb_ | #base-ui-_R_jajqatpesnfknebneitmlb_ | #base-ui-_R_lajqatpesnfknebneitmlb_"
```

Reproducible en dos ejecuciones completas y en una reejecución acotada (`-g`).

## Symptom

Las casillas de la lista blanca de herramientas (46) y las de «Cuándo escalar» /
«Permitir escalar» / «Aviso de IA» (6) no tienen nombre accesible para un lector
de pantalla hasta que React hidrata la página. axe, que escanea nada más cargar,
las marca como `aria-toggle-field-name`; un usuario de lector de pantalla que
llegue antes de la hidratación (o con JavaScript lento) oye «casilla, marcada» sin
saber de qué.

## Reproduction

1. Con sesión iniciada, `fetch('/clients/<ref>/tools').then(r => r.text())` y buscar
   `<span … role="checkbox"`: **0 de 46** llevan `aria-labelledby`. Tras hidratar,
   `document.querySelectorAll('[role=checkbox]')` sí lo tienen todas.
2. `pnpm exec playwright test e2e/a11y.spec.ts -g "view /tools"` → falla.

Una réplica manual con axe que espera a la hidratación sale limpia: por eso el
fallo parecía intermitente y no lo era.

## Suspected Code Paths

- `packages/ui/src/components/checkbox.tsx` — `Checkbox` es `CheckboxPrimitive.Root`
  de Base UI: renderiza `<span role="checkbox">` más un `<input>` oculto. El `id`
  que le pasa el consumidor va al **input**; el `<label htmlFor>` nombra al input,
  no al span. Base UI añade `aria-labelledby` al span en un efecto, en cliente.
- `apps/console/src/components/agent-tools/tools-catalog.tsx:171-175` —
  `<Checkbox id={id}>` + `<Label htmlFor={id}>`.
- `apps/console/src/components/agent-tools/agent-settings-form.tsx:352,370-378,440`
  — dos casillas dentro de `FormControl` (que solo pone `id` y `aria-describedby`) y
  cuatro con `<Label htmlFor>`.
- `packages/ui/src/components/form.tsx:104-116` — `FormControl` no enlaza la
  etiqueta por `aria-labelledby`.

## Root Cause Hypothesis

La asociación `label[for]` funciona para controles nativos; Base UI la traslada al
`span` con `aria-labelledby` solo tras montar. Todo lo que se renderiza en el
servidor queda sin nombre hasta entonces.

## Proposed Remediation

Enlazar la etiqueta explícitamente, en el servidor:

- `FormLabel` lleva `id={formLabelId}` y `FormControl` añade
  `aria-labelledby={formLabelId}` (un atributo más en los controles nativos, sin
  efecto; el nombre para los no nativos).
- En las casillas sueltas, `<Label id={`${id}-label`}>` y
  `<Checkbox aria-labelledby={`${id}-label`}>`.

## Files likely to change

- `packages/ui/src/components/form.tsx`
- `packages/ui/src/components/__tests__/form-ssr-name.test.tsx` (nuevo)
- `apps/console/src/components/agent-tools/tools-catalog.tsx`
- `apps/console/src/components/agent-tools/agent-settings-form.tsx`

## Tests to add or update

- DS: `renderToStaticMarkup` de un `FormControl` con `Checkbox` → el `<span
  role="checkbox">` lleva `aria-labelledby` y ese id existe en el HTML.
- La suite axe de CP-30 (ya existente) deja de fallar en las dos vistas.

## Risks & Considerations

- `aria-labelledby` explícito tiene prioridad sobre el que Base UI calcula: son el
  mismo elemento, así que no cambia el nombre.
- Otros consumidores de `FormControl` (desktop, companion-ui) reciben el atributo
  extra; para un `<input>` con `<label for>` es redundante y válido.

## Open Questions

- Ninguna.
