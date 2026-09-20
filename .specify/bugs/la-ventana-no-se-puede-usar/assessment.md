# Bug Assessment: la ventana no se puede usar

- **Slug**: la-ventana-no-se-puede-usar
- **Created**: 2026-09-20
- **Source**: auditoría de diseño del 2026-09-19 (hallazgos D1, D4, D5 y la primera
  mitad del P1-7), con 70 capturas
- **Verdict**: valid
- **Severity**: high
- **Vía**: flujo de bug normal. Son **defectos de lo que la spec 010 ya entregó**,
  no alcance nuevo: el armazón se construyó y nadie lo miró funcionando a tamaños
  distintos ni en oscuro.

## Symptom

Cuatro defectos que comparten consecuencia —la aplicación no se puede entregar a
nadie— y causa —se probó por piezas y no de frente—.

| # | Defecto | Dónde | Verificado |
|---|---|---|---|
| V1 | **El chat no tiene sitio.** El panel «Entorno» no declara ancho, así que se dimensiona a su contenido —rutas largas— y el hilo se queda con lo que sobre: **311 px de 1280, y 32 px en la ventana mínima (900×600)** | `app/routes/env.tsx` · `App.tsx:776-791` | medido en navegador |
| V2 | **Los bordes desaparecen en oscuro.** `--color-border` solo se declaraba en claro —tinta al 12 %— y el tema oscuro lo heredaba: tinta sobre tinta | `packages/ui/src/styles/tokens.css` | medido y en captura |
| V3 | **Una excepción de render deja la ventana en negro.** Sin `ErrorBoundary`, React desmonta el árbol entero; en Electron no queda barra de direcciones ni recarga | `app/main.tsx` · `i18n.ts` · `routes/pair-dialog.tsx` | reproducido en test |
| V4 | **Esqueleto perpetuo sin sesión.** `rosterStatus` se quedaba en `loading` para siempre: la lista lateral prometía algo que no venía | `App.tsx:229-232` | leyendo el código |

## Root cause

**V1 y V2 son el mismo error de método**: se miró cada pieza y no la ventana. Un
`aside` sin ancho es correcto en aislamiento y catastrófico junto a un hermano
`flex-1`; un token de marca declarado una vez es correcto hasta que hay dos temas.
Los dos se ven en cuanto alguien abre la aplicación a 1280 o en oscuro, y por eso
la auditoría los encontró con capturas y ninguna suite los tenía.

**V2 tiene además una trampa documentada.** `tokens.css` explica que `--color-border`
**no puede** espejarse en `@theme inline` porque crearía un `var()` circular que
Tailwind resuelve como inválido. Esa nota —correcta— dejó el token fuera del
puente de shadcn, y con ello fuera del bloque oscuro que sí redeclara `--border`.
Dos variables parecidas, una declarada por tema y la otra no.

**V3 nace de un tipo que promete lo que el servidor no firmó.** `t()` acepta
`AppKey`, y en un sitio la clave se arma en ejecución: ``t(`pair.error.${code}`)``
con un `as AppKey`. El código lo elige la plataforma; la tabla tiene tres. Y
`format()` hacía `COPY[key][lang]`, que sobre un `undefined` lanza **durante el
render**. El tipo protege el 99 % de los sitios y el 1 % restante es justo donde
nadie mira.

**V4** es el patrón de siempre: un `return` temprano que sale sin dejar el estado
en un valor terminal.

## Reproduction

- **V1**: servir el renderer con un puente falso y medir. Antes: `chat: 311` a
  1280×800 y `chat: 32` a 900×600. Script y medidas en
  `evidencia/scripts/medir.mjs` de la KB.
- **V2**: `contrast.test.ts` — el bloque oscuro no declaraba `--color-border`, así
  que resolvía al valor de claro.
- **V3**: `format("es", "pair.error.codigo_que_no_existe")` lanza `TypeError`.
- **V4**: arrancar sin sesión y mirar la lista lateral.

## Lo que este bug NO cubre, y por qué

La misma auditoría encontró tres cosas más en esta pantalla que **no son bugs**:
markdown sin renderizar, los mensajes propios que no vuelven al reabrir el hilo, y
la primera pantalla sin composer. Las tres son **capacidad que nunca se construyó**,
no comportamiento roto, así que entran por `/speckit-specify` —la spec 013, «la
conversación es el producto»— y no por aquí. Colarlas en un bug sería saltarse la
regla nº 1 del repositorio con la excusa de que están cerca.

Queda también la segunda mitad del P1-7: en el primer arranque la pantalla dice
«Tu sesión terminó» y «lo que escribiste sigue aquí», que es falso cuando nunca has
entrado. Arreglarlo bien pide distinguir «nunca entró» de «caducó», y ese dato hoy
no existe: `whoami` dice `anonymous` en los dos casos. Necesita una marca
persistida, y va con la 011 o la 012, que son las que tocan identidad.
