# Especificación: Cierre (el teléfono, axe y e2e)

**Rama**: `074-cierre` · **Creada**: 2026-11-22 · **Estado**: Decisiones D1–D2 del owner cerradas el 2026-11-22

**Entrada**: el owner abrió el lote 6 del roadmap de la consola (`[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`) con «vamos con el lote 6». El lote dice:
- el teléfono: una navegación, sin perder acciones (hallazgo M01);
- axe en todas las pantallas;
- e2e al día.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la consola de partners, que ya existe. |
| **Garantías de aislamiento tocadas** | **Ninguna.** Solo cambia cómo se pinta lo que la consola ya lee. |
| **Nota de KB que la justifica** | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`, lote 6. Hallazgo M01 (`docs/ux/consola-partners/findings.py`). |
| **Qué se mide** | **Nada nuevo.** |

## Qué hay hoy (2026-11-22, staging, 375 px)

- **Dos navegaciones a la vez.**
  - La cabecera lleva seis controles: logo, buscar, tema, campana, perfil y ☰.
  - Debajo hay una fila de secciones que se corta («Panel · Clientes · Consumo · Au…»).
  - El ☰ solo esconde esa fila.
- **Clientes esconde las columnas Agentes, Saldo y ⋯.** Desde el teléfono no se puede ver el saldo ni asignarlo, ni archivar.
- **e2e:** en el lote 4 aparecieron dos pruebas de Consumo que llevaban rotas desde el 30 de octubre. Nadie pasa todas las suites juntas.

## Requisitos

### 1. Una sola navegación en el teléfono (hasta 900 px)

- **1.1** La única navegación es una **barra inferior** (D1).
  - Lleva Panel, Clientes, Consumo y Auditoría, cada uno con icono y nombre.
  - Encima va la lente de vidrio de la 070, que viaja a la sección activa.
  - Cada sección es un enlace con `aria-current` y un objetivo táctil de 48 px.
  - La barra respeta la zona segura de abajo.
- **1.2** Se van la fila de secciones de arriba y el botón ☰.
- **1.3** Lo demás de «Operar» (la Guía del partner, Teammate) va en el menú del perfil, bajo «Operar». En la barra caben como mucho cinco secciones sin cortar el nombre.
- **1.4** El tema pasa al menú del perfil (D2): «Pasar a modo oscuro» o «Pasar a modo claro». La cabecera queda en logo, buscar, campana y perfil. Desde 901 px no cambia nada.

### 2. Clientes sin perder acciones

- **2.1** En el teléfono, cada cliente es una tarjeta con:
  - el nombre (enlace) y su nicho;
  - el estado;
  - los agentes, en texto y con sus puntos;
  - el saldo con su barra (`BagMeter`, de la 072);
  - el mismo menú ⋯ que en escritorio, con las mismas acciones y permisos.
- **2.2** Los objetivos táctiles miden al menos 44 × 44 px, el ⋯ incluido. La página no se desplaza de lado a 375 px.
- **2.3** El escritorio no cambia.

### 3. Accesibilidad

- **3.1** axe sin fallos «serious» ni «critical» en las pantallas del partner, en claro y en oscuro, y a 1280 y a 390 px:
  - Panel;
  - Clientes;
  - la ficha;
  - el agente;
  - Consumo;
  - Auditoría;
  - Facturación;
  - Equipo;
  - la campana y los avisos.
- **3.2** Cada fallo que aparezca se arregla en su componente, como regla del sistema, no con un parche en la prueba.

### 4. e2e al día

- **4.1** Pasan todas las suites de `apps/console/e2e/*.config.ts` y la configuración principal (`playwright.config.ts`). Las que esperan algo que el owner ya cambió se ponen al día con la regla nueva y se dice cuál era.
- **4.2** El e2e del marco (`shell.spec.ts`) mide la barra inferior a 390 px: una sola navegación, sin desbordes.

## Decisiones (owner, 2026-11-22)

- **D1 · La navegación del teléfono:** la barra inferior, con la lente de vidrio, como la app móvil. Se descartó el ☰ que abre el lateral como panel.
- **D2 · El tema en el teléfono:** en el menú del perfil. Se descartó dejarlo arriba.

## Fuera de alcance

- La app móvil (Auphere Customers), que tiene su propia spec.
- La licencia web de Helvena: queda pendiente del owner.
- Las cuatro pruebas del worker que ya fallaban en `develop` (el cobro por modelo y la agrupación de mensajes). Van aparte.
