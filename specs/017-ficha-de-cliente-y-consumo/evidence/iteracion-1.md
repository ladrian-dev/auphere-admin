# Iteración 1 · Ficha del cliente — evidencia

## Prototipo (T011)

- Story: `packages/ui/src/stories/prototypes/client-record.stories.tsx` (`Prototipos/Ficha de cliente`), doce estados: Falta canal · Atendiendo · Sin crédito asignado · Con borrador · Publicación fallida · Recién publicado · Canal caído · Crédito agotado · Analyst · Archivado · Cargando · Móvil.
- Cómo verlo: `preview_start storybook` (Node 24) → `http://localhost:6006/?path=/story/prototipos-ficha-de-cliente--con-borrador`.
- Addon a11y: sin violaciones (axe-core 4.13.0, 2026-09-24).
- **Aprobación del owner: 2026-09-25**, tras corregir la hoja «Revisar y publicar», que tenía tres sangrías distintas (título 17 px, tablas 1 px, pie sin margen).

Lo que el prototipo fija (las nueve decisiones aprobadas):

1. El estado de cabecera responde a «¿atiende ahora?» y nombra la causa: Atendiendo · Sin atender + causa · En pausa · Archivado. El ciclo de vida vive en el aviso y en «Más».
2. Cuatro pasos **en cualquier orden** (agente, canal, crédito, activación), sin ordinales ni conectores. WhatsApp no es el primer paso.
3. La ficha tiene dos vidas: «Puesta en marcha» mientras falta algo; Actividad y Crédito cuando atiende.
4. Diez pestañas en tres grupos (Observar · Configurar · Conectar); ninguna desaparece; `optgroup` en móvil.
5. Se publica desde cualquier pestaña, siempre pasando por la hoja de revisión, que dice autor, antigüedad y qué recorta el servicio.
6. Se puede deshacer durante diez minutos.
7. La unidad se llama «crédito»; la barra mide lo que queda.
8. Cada incidencia dice hora, causa, consecuencia y una salida; el analista ve «Avisar por correo al propietario», nunca un botón muerto.
9. Solo tres atajos: cliente anterior, siguiente e «Ir a cliente…». Las pestañas no llevan atajo.

### Medición del prototipo (crítica en dos agentes aislados)

| Vuelta | Diseño (Nielsen /40) | Detector | Contraste mínimo |
|---|---|---|---|
| 1.ª | 20 | limpio | — |
| 5.ª | 32 | limpio | 6,67:1 |
| 6.ª (Opus) | 29 | 0 hallazgos | 6,49:1 |
| 7.ª (Opus) | **30** | — | 6,7:1 |

Defectos P1 cerrados en la séptima y octava pasada, todos medidos: el `Button` del DS no pintaba foco (10 de 21 paradas sin indicador → 0); «Conocimiento» se salía 51 px a 390 px sin scroll; la insignia decía «Con incidencia» justo cuando el agente no atendía; la ficha archivada no decía qué pasaba con el crédito; el recorrido numerado contradecía «en cualquier orden»; y `credito-agotado` prometía «muévelo desde otro cliente» sin ofrecer dónde.

### Pendiente de decidir (no bloquea la iteración 1)

- Cifra del daño en una incidencia («N mensajes sin responder desde…»): necesita dato nuevo de la API, así que es cambio de spec.
- Contador vivo de la ventana de deshacer.
- Glosario de roles del producto: se ha fijado «propietario · administrador · editor · analista» en el prototipo; falta llevarlo a i18n (T002).
- Área de pulsación de 44 px bajo el punto de ruptura móvil.

## Cimientos ya en la rama (Setup + Foundational)

- API: `sector`, `setup` (+`next`), `quota` en la ficha; `setup`, `quota`, `conversations_7d` en la lista; `CATEGORY_LABELS`; migración 0129.
- Tests: `tests/unit/test_console_audit_vocab_017.py`, `tests/integration/test_console_client_setup.py` (8 casos), suites `-k console` (185) e isolation `test_console_scope.py` en verde el 2026-09-24.
- `scripts/verify.sh locks` en verde (lockfiles sin cambios).

## Implementación de la iteración 1 (2026-09-26)

### Qué se recorrió en el stack local

Partner `demo-audit`, cliente «Panadería La Espiga» (agente publicado, canal
solo `web`, 50 000 créditos). Recorrido completo con el propietario:

1. **Cabecera**: «Sin atender» con los cuatro pasos —Agente ✓, Canal
   pendiente, Crédito ✓, Activación ✓— sin ordinales ni conectores, un solo
   botón («Conectar un canal») y su porqué debajo. Crédito al lado.
2. **Menú «Más»**: Suspender · Archivar · Copiar referencia, cada uno con su
   descripción. Sin «Eliminar», porque el cliente no está archivado.
3. **Pestañas**: tres grupos, punto azul en «Ajustes» (borrador) y rojo en
   «Canales» (incidencia).
4. **Barra de borrador** visible desde **Conversaciones**, que es lo que
   antes no se podía.
5. **Hoja «Revisar y publicar»** con el diff real: una sola fila,
   «Identidad · sin definir → Se presenta como «Espiga»».
6. **Publicar → deshacer**: «Versión 2 publicada · Deshacer vuelve a la
   versión 1 · quedan 10 min» → Deshacer → versión 1 activa.
7. **Historial**: «v3 · Borrador · Cambia: Ajustes».

### Suites

| Suite | Resultado |
|---|---|
| `@nexus/ui` (unidad) | 144 ✅ |
| `console` (unidad) | 409 ✅ |
| API `-k console` | 842 ✅ |
| API aislamiento | 1 109 ✅ |
| e2e `a11y.spec.ts` + `record.spec.ts` | 30 ✅ · 2 saltadas (builder y analyst, sin credenciales en el entorno) |

axe sin violaciones graves ni críticas, sin desbordamiento a 360 ni 1 920 px
—tampoco con el texto inflado un 30 %— y en ES y EN.

### Defectos que solo aparecieron al ejecutarlo

Ninguno de los cinco lo veían los tests, porque todos simulan el backend o
construyen datos limpios:

1. **422 al publicar**: el ayudante del BFF serializa el cuerpo, y se le
   pasaba ya serializado.
2. **El punto de «sin publicar» señalaba la pestaña equivocada**: «Ajustes»
   apuntaba a los datos del cliente, no a los del agente.
3. **La hoja listaba seis cambios habiendo uno**: el formulario escribe la
   política entera, así que los huecos que rellena por defecto aparecían
   como decisiones.
4. **Los valores se pintaban en JSON crudo** en vez de decirse en una frase.
5. **Dos defectos fuera de esta spec**, cazados por la barrida: la pista del
   selector de modelo se salía de 360 px con una traducción más larga, y el
   interruptor de alertas de consumo no tenía nombre accesible.

### Lo que queda antes de cerrar la iteración

Ver `parity.md`: 5 filas pendientes (migas, zona horaria, teléfono, detalle
al pasar por un paso, «Atendiendo desde») y 2 parciales (asignar crédito sin
salir de la ficha, y plegar el diff del prompt dentro de la hoja). Ninguna
bloquea el uso; **falta la decisión del owner** sobre si entran ahora o se
difieren.
