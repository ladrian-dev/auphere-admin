# Especificación: el módulo de Clientes, cómodo y claro

**Rama**: `035-canales-y-conectores` (continúa) · **Creada**: 2026-10-19 · **Estado**: Aprobada para implementar

**Entrada**: owner, 2026-10-19 — «Mejoremos la UI en el módulo de clientes, vista de todos
los clientes y vista detallada de un cliente. Que sea cómoda, intuitiva, con una excelente
UX y UI. Analiza leyes de heurística, leyes jerárquicas, usabilidad intuitiva y flujo
ordenado.»

## Encabezado Auphere

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — panel de operador |
| **Garantías de aislamiento tocadas** | **1** — la lista lee la salud de cada cliente **con su GUC** (`tenant_scoped_session`), igual que la spec 035. Test en `tests/integration/test_admin_tenants_health.py` |
| **Nota de KB** | `[[ADR-047-clientes-comodos]]` |
| **Qué se mide** | Nada nuevo |

## 1. Para quién y para qué

El operador de Auphere entra en Clientes con **tres preguntas**, en este orden de
frecuencia:

1. **¿Quién necesita algo de mí?** Un canal caído, un agente sin publicar, un conector que
   pide reconectar, un cliente nuevo a medio montar.
2. **¿Dónde está tal cliente?** Lo busca por nombre, número o partner.
3. **¿Cómo está este cliente?** Abre su ficha para revisar o cambiar algo.

Hoy la pantalla responde bien a la segunda y mal a la primera y la tercera.

## 2. Marco de análisis

Se evaluó con estos principios. Cada hallazgo de §3 cita el que incumple.

**Heurísticas de Nielsen (H1–H10)**

- H1 Visibilidad del estado del sistema.
- H2 Coincidencia con el mundo real.
- H3 Control y libertad.
- H4 Consistencia y estándares.
- H5 Prevención de errores.
- H6 Reconocer antes que recordar.
- H7 Flexibilidad y eficiencia.
- H8 Diseño estético y minimalista.
- H9 Ayudar a reconocer y corregir errores.
- H10 Ayuda y documentación.

**Leyes de UX**

- **Hick**: más opciones a la vista, decisión más lenta. Se agrupa y se dan atajos.
- **Fitts**: el objetivo frecuente, grande y cerca. La fila entera es el objetivo.
- **Miller**: unos 7 elementos en memoria de trabajo. Grupos de 3 o 4.
- **Jakob**: la gente espera que funcione como lo que ya usa (Chatwoot, Stripe, Linear).
- **Tesler**: la complejidad no desaparece. La absorbe el sistema, no el operador.
- **Doherty**: la respuesta en menos de 400 ms mantiene el ritmo. Filtrado en el cliente.
- **Von Restorff**: lo distinto se recuerda. Solo lo que necesita atención destaca.
- **Posición serial**: lo primero y lo último se recuerdan. Lo urgente arriba.
- **Gradiente de objetivo**: ver cuánto falta motiva a terminar («3 de 4 pasos»).

**Jerarquía visual y Gestalt**

- **Patrón F**: en listas densas se lee la primera columna y se baja. La primera columna lleva identidad y la señal.
- **Proximidad y región común**: lo que va junto se agrupa en un mismo bloque.
- **Similitud**: un estado se dice siempre igual (punto + palabra).
- **Divulgación progresiva**: lo que no hace falta ahora se pliega.

## 3. Auditoría (medida el 2026-10-19 en local)

### Lista de clientes

| # | Hallazgo | Principio | Arreglo |
|---|---|---|---|
| L1 | Todas las filas se ven iguales: nada dice qué cliente tiene un canal caído o un agente sin publicar | H1, Von Restorff | Columna de salud con motivo en palabras; vista «Necesitan atención» |
| L2 | El orden no tiene criterio (un cliente a medio montar sale primero por casualidad) | Posición serial | Orden por defecto: lo que necesita atención primero, después por nombre; columnas ordenables |
| L3 | Tres desplegables de filtro de igual peso | Hick, H7 | Estado como pestañas con contador; partner y plan como filtros secundarios |
| L4 | Columnas «Actualizado» y «Mensualidad» repiten el mismo valor en todas las filas | H8 | Fuera «Actualizado». «Mensualidad» solo si algún cliente tiene plan mensual |
| L5 | Solo el nombre es clicable | Fitts | La fila entera abre la ficha; el menú de acciones sigue aparte |
| L6 | Un estado sale en crudo: «provisioning» | H2, H4 | «Preparando», con el mismo punto que el resto |
| L7 | No se ve el canal ni la actividad | H6 | Columna Canal (logo + número) y «Última conversación» |
| L8 | Los filtros se cortan («Todos los estado») | H8 | Controles con ancho propio; el contador va en las pestañas |
| L9 | Al volver de una ficha, el filtro se pierde | H3, H7 | Búsqueda, pestaña, orden y filtros viven en la dirección |

### Ficha del cliente

| # | Hallazgo | Principio | Arreglo |
|---|---|---|---|
| F1 | Cabecera, hechos y dos filas de pestañas ocupan media pantalla antes del contenido | H8, patrón F | Cabecera compacta; pestañas en una sola fila con separadores de grupo |
| F2 | Los hechos son números sueltos («1», «0») | H6 | Hechos con su forma: logo y número del canal, versión del agente, última conversación |
| F3 | La única acción visible es «Acciones»; la tarea más frecuente (probar el agente) está escondida en el Resumen | Fitts, H7 | «Probar agente» como botón principal en la cabecera |
| F4 | La lista de comprobación se ve igual con todo hecho | Divulgación progresiva, Von Restorff | Con todo hecho, una línea; si no, solo lo pendiente arriba con «3 de 4» |
| F5 | El Resumen no enseña actividad | H1 | «Conversaciones recientes» en el Resumen |
| F6 | El Resumen es una columna larga de bloques iguales | Patrón F, proximidad | Dos columnas en escritorio: a la izquierda lo que se hace, a la derecha los datos |
| F7 | Conversaciones habla en jerga («POLLING», «AGENTE ON», «stream del backend», «tenant») | H2 | Español claro: «En vivo», «El agente responde», «Tomada por una persona» |

## 4. Requisitos (EARS)

### R1 — Salud de cada cliente

1. La API DEBE exponer `GET /admin/tenants-health`. Por cliente da canales activos y con problemas, el canal principal, la versión publicada del agente, conversaciones abiertas, la última actividad y los conectores por reconectar.
2. DEBE leer cada cliente con su GUC y nombrar en `unreadable` al que no pudo leer.
3. NO DEBE contar las conversaciones del Playground.

### R2 — Lista

1. La lista DEBE ofrecer las vistas Todos, Necesitan atención, Activos, En pausa y Archivados, cada una con su contador.
2. CUANDO un cliente necesita atención, la fila DEBE decir el motivo en palabras.
3. El orden por defecto DEBE poner primero lo que necesita atención.
4. Búsqueda, vista, orden y filtros DEBEN vivir en la dirección.
5. La fila entera DEBE abrir la ficha, con el teclado también.

### R3 — Ficha

1. La cabecera DEBE caber en un tercio de la pantalla a 1440 × 900, con las pestañas en una fila.
2. «Probar agente» DEBE estar en la cabecera.
3. El Resumen DEBE poner primero lo pendiente, enseñar las conversaciones recientes y plegar la lista de comprobación cuando no falte nada.
4. Conversaciones NO DEBE usar jerga técnica.

## 5. Criterios de éxito

- **CE-001**: desde la lista, en un vistazo, se sabe qué clientes necesitan algo y por qué.
- **CE-002**: en la ficha, el contenido empieza en el primer tercio de la pantalla.
- **CE-003**: probar el agente de un cliente lleva un clic desde su ficha.

## 6. Fuera de alcance

- Acciones en lote sobre varios clientes.
- Columnas configurables por el operador.
