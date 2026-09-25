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
