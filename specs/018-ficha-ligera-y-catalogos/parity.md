# Paridad · nada desaparece sin decisión escrita

Inventario hecho el **2026-09-27, antes de tocar una línea**, leyendo las
pantallas de hoy en `develop`. Una fila por cosa que la consola enseña o
permite, con su destino.

**Leyenda**: ✅ se conserva igual · ➡️ se mueve · ➕ es nuevo · ❌ se retira con
decisión escrita · ⚠️ pendiente de decidir.

---

## Iteración 1 · La ficha (US1, US2, US5) — **cerrada el 2026-09-27**

Filas 1–37, todas. Comprobadas sobre la aplicación real, no sobre el
código: nueve pestañas, las dos URLs retiradas caen donde deben, y los
ajustes del agente se leen dentro de «Agente».

### Lo que hoy hay en el Resumen (`clients/[ref]/page.tsx`)

Fuente: 86 líneas. Todo lo que enseña, enumerado.

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 1 | Punto de estado + título «listo» / «le falta X» | Bloque **¿Atiende?**, misma frase | ✅ |
| 2 | Subtítulo con versión del agente y estado de WhatsApp | Al bloque **¿Atiende?**, junto al resto de la salud | ➡️ |
| 3 | Aviso «sin crédito» con enlace a asignar, solo si `usage:write` | Al bloque **¿Cuánto consume?**, donde está la cifra que lo explica | ➡️ |
| 4 | Botones del paso que falta, filtrados por permiso | Se quedan donde el usuario los espera: en la puesta en marcha (fila 12) | ➡️ |
| 5 | Botón «Agente» cuando ya está listo | ✅ dentro de **¿Atiende?** | ✅ |
| 6 | Métrica «Conversaciones» → lista | Bloque **¿Cómo va la conversación?** | ✅ |
| 7 | Métrica «Escaladas» → lista filtrada | Ídem | ✅ |
| 8 | Métrica «Mensajes fallidos» → lista filtrada | Ídem | ✅ |
| 9 | Las métricas **desaparecen** si el rol no lee conversaciones | Se conserva: el bloque no existe en vez de existir vacío | ✅ |
| 10 | — | Bloque **¿Cuánto consume?**: créditos restantes, gasto del mes, proyección | ➕ |
| 11 | — | Bloque **¿Qué tiene conectado?**: canales y conectores con su estado | ➕ |

### Lo que hoy hay en la cabecera (`client-setup.tsx`)

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 12 | «Puesta en marcha»: cuatro pasos sin ordinales, con el dato de cada uno hecho («Agente · versión 3», el teléfono del canal) | Se conserva entero, **solo** mientras falte algo | ✅ |
| 13 | Contador «N de 4 pasos hechos» | Se conserva | ✅ |
| 14 | Un solo botón, el del paso pendiente | Se conserva: un botón, no cuatro | ✅ |
| 15 | Cuando el rol no puede resolverlo, dice **quién** puede, en vez de un botón que daría 403 | Se conserva | ✅ |
| 16 | Línea de «por qué importa» del paso pendiente | Se conserva | ✅ |
| 17 | La puesta en marcha **desaparece** cuando los cuatro pasos están | Se conserva | ✅ |
| 18 | Tarjeta de crédito **al lado**, con su medidor de tres tonos y «Cambiar crédito» | ➡️ **al Resumen**, como bloque «¿Cuánto consume?». Deja de compartir fila con la puesta en marcha, que es lo que la hacía pesada (R6.1) | ➡️ |
| 19 | El crédito sigue visible cuando la puesta en marcha desaparece | Se conserva — por eso el crédito **no** puede ser parte de la puesta en marcha (R6.2) | ✅ |
| 20 | Ayuda contextual sobre qué es el crédito | Se conserva en su bloque | ✅ |
| 21 | «Sin tope configurado» cuando no hay cuota | Se conserva | ✅ |

### Lo que hoy hay en «Datos del cliente» (`settings/page.tsx`)

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 22 | Campo: nombre del cliente | ➡️ Al Resumen, editable ahí mismo | ➡️ |
| 23 | Campo: zona horaria | ➡️ Ídem | ➡️ |
| 24 | La pantalla entera, con su pestaña | ❌ La pestaña se retira (R2.2). La URL sigue viva como redirección (R2.3) | ❌ (decisión escrita: R2.2) |
| 25 | Guardar **no** toca el borrador del agente | Se conserva, y ahora tiene test propio (R2.4) | ✅ (mejor) |

### Lo que hoy hay en «Ajustes» del agente (`agent/settings/`)

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 26 | Sección «Identidad» | ➡️ Dentro de «Agente» | ➡️ |
| 27 | Sección «Tono» | ➡️ Ídem | ➡️ |
| 28 | Campo «Objetivo» | ➡️ Ídem | ➡️ |
| 29 | Sección «Horario» con su lista de tramos | ➡️ Ídem | ➡️ |
| 30 | Sección «Idiomas» | ➡️ Ídem | ➡️ |
| 31 | Sección «Escalado» | ➡️ Ídem | ➡️ |
| 32 | Sección «Aviso de IA» | ➡️ Ídem | ➡️ |
| 33 | Validación de horas, zona y turnos | Se conserva entera | ✅ |
| 34 | Aviso de solo lectura sin `agents:write` | Se conserva | ✅ |
| 35 | Toast de guardado con enlace a publicar | Se conserva | ✅ |
| 36 | La pestaña «Ajustes» | ❌ Se retira (R3.1); la URL redirige a «Agente» (R3.3) | ❌ (decisión escrita: R3.1) |
| 37 | El punto de borrador señalaba «Ajustes» | ➡️ Señala «Agente», que es donde ahora vive el cambio (R3.2) | ➡️ |

---

## Iteración 2 · Los catálogos (US3)

### Habilidades (hoy «Capacidades», `capabilities/`)

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 38 | Buscador por nombre de negocio y descripción | Se conserva, dentro del patrón común | ✅ |
| 39 | Contador «n de N encendidas» con `aria-live` | Pasa a ser el del patrón, «{visibles} de {total} · {activos} activos», con el mismo `aria-live`. Dice **más**: cuántos hay en total, que es lo que «1» a secas se callaba | ➡️ |
| 40 | Agrupación por función, sin grupos vacíos | Se conserva: la función pasa a ser **la categoría** del patrón | ✅ |
| 41 | Filtro por sector con «Ver todas» y cuántas oculta, en la URL | Se conserva **dentro** del patrón nuevo, no al lado | ➡️ |
| 42 | «Encender / apagar las visibles» | Se conserva | ✅ |
| 43 | Bloque de integraciones que estorban, arriba | Se conserva | ✅ |
| 44 | Conmutador que guarda al clic; modo; insignias; detalle técnico plegado | Se conservan enteros | ✅ |
| 45 | — | Pestañas para ver solo lo activo o todo | ➕ |
| 46 | — | Filtro por categoría, en pastillas con su cuenta: además de filtrar, son el mapa de lo que hay dentro | ➕ |

### Conectores (hoy «Integraciones», `integrations/`)

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 47 | Contador «n de N conectadas» | El mismo contador del patrón que en Habilidades, palabra por palabra (R4.6) | ➡️ |
| 48 | Orden por lo que necesita atención | Se conserva **dentro de cada grupo** | ➡️ |
| 49 | «Desbloquea N capacidades» por integración | Se conserva (dirá «habilidades») | ✅ |
| 50 | Conectar · reconectar · sincronizar · pausar · reanudar · desconectar con confirmación | Se conservan **todas**, con otra forma: conectar es un `+`, reconectar sigue siendo un botón con texto —un error tiene que poder leerse— y el resto vive en «Más», como en la cabecera de la ficha (owner, 2026-09-28) | ➡️ |
| 51 | Diálogo de clave de API con campos traducidos; AgendaPro por URL pública | Se conservan enteros | ✅ |
| 52 | Alerta cuando los conectores no cargan | Se conserva | ✅ |
| 53 | Sin buscador, sin filtros, sin categorías | Los gana del patrón | ➕ |
| 53b | La tarjeta era nombre + cuatro datos en una línea + hasta cinco botones | Icono de la aplicación, nombre, **para qué sirve** y una acción; lo que se sabe de él, debajo y en gris (owner, 2026-09-28) | ➡️ |
| 53c | El estado solo en una insignia | Punto en el icono **y** palabra en la línea de abajo; la insignia se reserva para lo que necesita explicación —pausado, roto, caducado— (owner, 2026-09-28) | ➡️ |

### Canales (`channels/`)

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 54 | Rejilla de tarjetas de canal, con su gestión | Se conserva dentro del patrón | ➡️ |
| 55 | Aviso de roles requeridos | Se conserva | ✅ |
| 56 | Estado vacío con acción de conectar | Se conserva, distinguido del vacío por filtro | ✅ |
| 57 | Sección de plantillas, debajo | Se conserva **fuera** del catálogo: una plantilla no es un canal | ✅ |
| 58 | Enlace a diagnósticos del canal | Se conserva | ✅ |
| 59 | Sin buscador, sin filtros | Los gana del patrón | ➕ |
| 60 | — | Un canal que todavía no se puede conectar **no** se enseña (R4.7) | ➕ |

---

## Iteración 3 · Las palabras (US4)

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 61 | La pantalla se llama «Capacidades» | **Habilidades**, ES y EN | ➡️ (R5.1) |
| 62 | La pantalla se llama «Integraciones» | **Conectores**, ES y EN | ➡️ (R5.1) |
| 63 | Rutas `/capabilities` e `/integrations` | Se conservan; el renombrado es de lo que se ve (Fase 0, decisión 3) | ✅ |
| 64 | «Conocimiento» dice qué es, no **quién lo lee** | Lo dice (R5.2) | ➕ |
| 65 | «Guía del partner» dice que el Companion la ve y el agente no | Se conserva y se sube a la cabecera, donde se lee (R5.3) | ➡️ |

---

## Decisiones que esta spec toma, y que hay que poder citar

1. **Filas 24 y 36** — dos pantallas se retiran. Ninguna función se pierde: las
   filas 22, 23 y 26–35 dicen adónde va cada una, y sus URLs siguen vivas.
2. **Fila 18** — el crédito deja de compartir fila con la puesta en marcha. Es
   el arreglo de la anotación 8 del owner, y la fila 19 explica por qué no
   podía quedarse dentro: sobrevive cuando la puesta en marcha desaparece.
3. **Fila 60** — la ausencia se diseña (§V). Un canal que no se puede conectar
   no es un elemento del catálogo apagado: no está.

## Lo que esta spec NO toca

- El menú «Más» de la cabecera y el ciclo de vida del cliente.
- La barra de borrador y la hoja de revisión.
- `/usage`, que es la iteración 3 de la spec 017.
- Conversaciones, Playground, Conocimiento (contenido), Puesto de trabajo.
