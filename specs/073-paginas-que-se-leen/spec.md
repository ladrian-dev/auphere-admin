# Especificación: Páginas que se leen

**Rama**: `073-paginas-que-se-leen` · **Creada**: 2026-11-21 · **Estado**: Borrador, decisiones del owner cerradas el 2026-11-21 (D1–D3); pendiente de la revisión de Luis

**Entrada**: el owner dio paso al lote 5 del roadmap de la consola (`[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`) mientras el lote 3 sigue con sus pruebas: «vamos a continuar con el lote 5 mientras el lote 3 sigue con sus pruebas». El lote dice:
- Auditoría como tabla;
- los menús del cliente y del agente;
- Negocio.

Por decisión del owner (D2) entran también dos hallazgos de la página del agente que el roadmap no ponía en ningún lote: la configuración que no se lee (A01) y los avisos repetidos (A04).

El roadmap dejaba una duda abierta: si la API sabe pausar y archivar un agente. **Ya sabe.** `agent-menu.tsx` llama a renombrar, pausar, reanudar, archivar, restaurar y «por defecto», y todas esas acciones existen. Lo que falta es «Deshacer» (§3).

**No depende de la 071 ni de la 072.** No toca el Panel, ni Consumo, ni la campana, así que se puede programar en paralelo. Solo comparte una pieza: «Asignar saldo», que sale del menú del cliente. El menú solo abre el diálogo, y lo que cambia dentro del diálogo es de la 072.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la consola de partners y la API de la consola, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **1 (RLS / partner)**, rozada. Auditoría pasa a nombrar a cada persona por lo que es («cliente · Meta Review Demo»), y para eso lee a las personas de los clientes del partner. Plan: un test que barre la auditoría de dos partners y comprueba que ninguno ve el nombre de una persona del otro, ni de un cliente que no es suyo. |
| **Nota de KB que la justifica** | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`, lote 5. Hallazgos del recorrido de staging del 2026-11-20: D01 y D02 (Auditoría), C02 y F02 (menú del cliente), A01 y A04 (página del agente), B01, B02 y T01 (Negocio). Decisiones de la demo v4 y v6. |
| **Qué se mide** | **Nada nuevo.** No llama a modelos ni a herramientas de pago. |

## Qué hay hoy (2026-11-21, `develop` en c4c44def)

### 1. Auditoría no cabe y la llenan los accesos

`app/(console)/audit/audit-table.tsx` tiene seis columnas de ancho fijo:

| Columna | Ancho |
|---|---|
| Hora | `w-36` |
| Persona | `w-44` |
| Qué pasó | `min-w-80` |
| Cliente | `w-40` |
| Categoría | `w-32` |
| Acciones | `w-12` |

Suman unos 976 px. A 1280 px, con la barra lateral abierta, la tabla se sale por la derecha y «Categoría» queda en «A…». WCAG 1.4.10 pide que el contenido no obligue a desplazarse en dos direcciones (D01).

Además:
- Los días no se separan. La hora lleva la fecha en cada fila.
- Los inicios y cierres de sesión llenan casi todas las filas y entierran los cambios de topes, saldo y catálogo (D01). Los filtros (cliente, persona, categoría y periodo) no tienen un modo que los aparte.
- La misma persona aparece como «Andres» y como su correo (D02). `actorName` usa el nombre de la lista de personas si lo encuentra y, si no, lo que trae el evento.
- No se distingue a las personas del partner de las de un cliente.
- El origen contradice el evento: «entró en la app desde iPhone 17» lleva la etiqueta «Desde la web» (`audit.v2.origin.*`).

### 2. El menú del cliente

`components/clients/v2/client-menu.tsx` ofrece lo que manda la API en `allowed` (`client_actions` en `console_home_blocks.py`):
- Editar;
- Asignar o Pedir saldo;
- Archivar o Restaurar, con Deshacer al archivar;
- Eliminar.

Lo que falla:
- **En la ficha, el ⋯ solo sale si el cliente no está activo** (`client-header-v2.tsx`, `{!active ? … : null}`). Un cliente activo no tiene menú en su propia ficha. Sí lo tiene en la lista de Clientes (F02).
- **«Eliminar» se ofrece en un cliente activo.** `client_actions` añade `delete` con solo tener `clients:delete`, esté archivado o no. El diálogo pide escribir el nombre, y solo después el servidor responde «Archívalo antes de eliminarlo» (C02).

### 3. El menú del agente

`components/builder/agent-menu.tsx` ya tiene todas las acciones: renombrar, pausar, reanudar, archivar, restaurar y «por defecto». Pero al pausar y al archivar solo sale un aviso de éxito («… pausado», «… archivado»), sin Deshacer. La demo aprobada (v6) lo pide en las dos.

### 3b. La configuración del agente no se lee

En `components/builder/agent-builder.tsx`:
- **A01**: cada bloque de la configuración va en tres columnas (etiqueta · texto · lápiz) dentro de media página. A 1280 px el texto queda en una columna de unos 110 px, a unos 22 caracteres por línea. A 820 px, en una sola columna, se lee mejor que en escritorio.
- **A01**: la columna de pruebas, a la derecha, es `sticky` con su propio `overflow-y-auto` y `max-h`. Mide unos 3.615 px y se desplaza por su cuenta, así que la rueda mueve una columna u otra según dónde esté el puntero.
- **A04**: «18 sin ejecutar» sale tres veces: en la cabecera, en el bloque «Pruebas» de la columna derecha y en la barra pegajosa de abajo («Pruebas sin ejecutar · Ejecutar pruebas»).
- **A04**: después sale un aviso por servicio sin precio, 56 veces: «X no tiene precio: el agente dirá que lo confirma el equipo. Ir a Servicios».

### 4. Negocio es una página de 25 pantallas

En staging: 18.661 px, con 56 servicios y 60 preguntas, todo desplegado (B01).
- **Servicios** ya se agrupan por categoría, con filas de grupo (`services-section.tsx`, `byCategory`). Pero todos los grupos están abiertos y no hay buscador. Además, cada fila repite «No se reserva · Sin precio · Ava» cuando ninguno tiene precio ni reserva.
- **Preguntas**: cada una enseña su respuesta entera con «Editar» y «Quitar» a la vista.
- **Revisar lo leído de la web**:
  - la API confirma **por sección** (`POST /sections/{section}/confirm`, «Es correcto», requisito 13.2);
  - la consola tiene el botón en `provenance-label.tsx`, pero solo con `review && canConfirm`;
  - en staging no apareció. La ficha decía «13 datos por revisar» y no había forma de revisarlos (B02);
  - el índice de secciones enseña un globo en lugar de cuántos faltan.
- **Etiquetas**: la cabecera dice «Europe/Madrid · EUR» sin decir qué es cada cosa. Lo leído en inglés se enseña en inglés sin avisarlo (T01).

## La propuesta

**Que cada página se pueda leer de arriba abajo sin desplazarse de lado, sin repetir lo mismo en cada fila y sin enterrar lo que importa.**

- **Auditoría**:
  - una tabla que cabe a 1280 px, con los días como filas de grupo;
  - cada persona dice qué es y el origen coincide con el evento;
  - «Solo cambios» por defecto: los accesos quedan en «Todo, con accesos».
- **El menú del cliente**:
  - el ⋯ siempre está, en la ficha y en la lista;
  - la regla de eliminar se dice antes y no después: en un cliente activo, «Eliminar…» explica que primero hay que archivarlo y ofrece «Archivar ahora».
- **El menú del agente**: Deshacer al pausar y al archivar, como ya hace el cliente al archivar.
- **La configuración del agente**:
  - la etiqueta encima del texto, que va a unos 70 caracteres por línea, y un «Editar» por bloque;
  - las pruebas se mueven con la página;
  - cada aviso sale una vez.
- **Negocio**:
  - un buscador arriba;
  - los grupos de servicios se pliegan;
  - las columnas que nadie usa se resumen en una línea;
  - las preguntas se pliegan;
  - revisar lo leído se puede hacer, por sección, y se ve cuánto falta (D1).

## Requisitos

### 1. Auditoría

1.1 **Cabe sin desplazarse de lado** a 1280 px, con la barra lateral abierta o plegada:
- «Qué pasó» toma el ancho que queda, sin `min-w-80`;
- Persona, Cliente y Categoría se cortan con su texto entero en `title` y en el nombre accesible;
- a 390 px, la tabla sigue plegando persona, cliente y categoría dentro de «Qué pasó», como hoy.

1.2 **Los días son filas de grupo** («Hoy», «Ayer», «jueves 19 nov»), con `scope="colgroup"`. La columna Hora solo dice la hora.

1.3 **Cada persona dice qué es**:
- «tú · partner», para quien mira;
- el nombre y «partner», para otra persona del equipo;
- el nombre y «cliente · Meta Review Demo», para una persona de un cliente;
- «Auphere · plataforma», con un icono neutro y no con el logo;
- la clave de API, como hoy.

1.4 **Una persona, un nombre.** La API resuelve el nombre del actor por su usuario cuando lo tiene, y solo pone el correo si no hay nombre. «Andres» y su correo no salen como dos personas.

1.5 **El origen coincide con el evento.** La etiqueta de origen sale del mismo dato que la frase:
- «Desde la app de iPhone» si entró desde la app;
- nada si fue la consola web, como hoy.

Un evento sin origen conocido no lleva etiqueta.

1.6 **«Solo cambios» por defecto.**
- Una cápsula de vidrio (`SegmentedControl`) con «Solo cambios» y «Todo, con accesos» va junto a los filtros.
- Son accesos (D3): iniciar sesión, cerrar sesión, renovar la sesión y los intentos fallidos. Todo lo demás es un cambio.
- La elección va en la URL, y «Descargar CSV» respeta la misma vista.

1.7 «Más como esta», las acciones de cada fila («Solo este cliente», «Solo esta persona»…) y «Ver anteriores» siguen como hoy.

### 2. El menú del cliente

2.1 **El ⋯ siempre está**, en la ficha y en la lista, también con el cliente activo. La píldora de estado sigue saliendo solo si no está activo, como hoy.

2.2 **La API dice si se puede eliminar.**
- `client_actions` sigue mandando `delete` a quien tiene `clients:delete`.
- Junto a las acciones, manda por qué no se puede todavía: `delete_blocked: "archive_first"` en un cliente activo y `null` en uno archivado.
- La consola no deduce la regla: la lee.
- El servidor sigue rechazando eliminar un cliente activo, como hoy.

2.3 **En un cliente activo**:
- «Eliminar…» sale en rojo, con una segunda línea: «Primero hay que archivarlo».
- Al elegirlo se abre un diálogo **sin campo de nombre**. Explica por qué («Eliminar no se deshace; archivar sí») y ofrece «Archivar ahora».
- Archivar desde ahí hace lo mismo que «Archivar» del menú: Deshacer y, si sobra saldo, devolverlo.

2.4 **En un cliente archivado**, «Eliminar para siempre…» pide escribir el nombre, y el botón solo se enciende entonces. Es el `ConfirmDialog` con `typeToConfirm` de hoy.

2.5 El menú se abre bajo su botón, alineado a su borde derecho, y se cierra con Esc o con un clic fuera. Es el desplegable de hoy (demo v4).

2.6 **La spec 062** (`062-borrar-cliente-facturado`, en su rama, sin fusionar) cambia qué se borra en el servidor. Esta spec solo cambia cómo se presenta. Si la 062 añade otro motivo para no poder eliminar, viaja en el mismo `delete_blocked`, con su texto.

### 3. El menú del agente

3.1 Pausar deja un aviso con **Deshacer**, que reanuda el agente.

3.2 Archivar sigue preguntando antes, con el diálogo de hoy que pregunta adónde van sus canales. Su aviso lleva **Deshacer**, que lo restaura.

3.3 Si Deshacer falla (por ejemplo, porque otro agente ya ocupa el canal), lo dice con el error de hoy y no deja el agente a medias.

3.4 El menú es el mismo desplegable que el del cliente (2.5). Las acciones no cambian.

### 3b. La configuración del agente (D2)

3b.1 **Cada bloque se lee en una columna**:
- la etiqueta va encima del texto;
- el texto tiene una medida de unos 70 caracteres por línea (`max-w-prose` o equivalente);
- cada bloque lleva un solo «Editar», en lugar del lápiz en una tercera columna.

3b.2 **La columna de pruebas se mueve con la página.** Deja de tener scroll propio: sin `max-h` ni `overflow-y-auto`. Por debajo de 1060 px pasa bajo la configuración, como hoy.

3b.3 **«Pruebas sin ejecutar» sale una vez**, en el bloque «Pruebas»:
- «18 pruebas sin ejecutar»;
- con «Ejecutar las 18 pruebas» y lo que cuestan («unos 0,40 USD»), con el mismo cálculo de coste que ya usa la consola;
- la cabecera y la barra pegajosa de abajo dejan de repetirlo. La barra se queda solo para guardar o publicar.

Si el coste no se puede calcular, el botón no inventa una cifra: dice lo que ya dice hoy («No se puede calcular el coste»).

3b.4 **Los servicios sin precio se resumen en una línea**: «56 servicios no tienen precio: el agente dirá que lo confirma el equipo», con «Poner precios», que lleva a Servicios en Negocio. Si es uno solo, la línea lo nombra.

3b.5 Lo que no cambia: las pestañas del agente, lo que se puede editar y cómo se guarda.

### 4. Negocio

4.1 **Un buscador** arriba de Negocio:
- filtra servicios y preguntas por su texto y dice cuántos encuentra («4 servicios y 2 preguntas»);
- va en la URL (`?q=`);
- vacío, la página es la de siempre.

4.2 **Los grupos de servicios se pliegan:**
- cada grupo dice cuántos tiene;
- con más de 12 servicios, empiezan plegados salvo el primero;
- al buscar, se abren los grupos con resultados.

4.3 **Las columnas que nadie usa se resumen.** Si ningún servicio tiene precio, desaparece la columna de precio y una línea lo dice una vez: «Ninguno de los 56 tiene precio, así que su agente dirá que lo confirma el equipo», con «Poner precios». Lo mismo con «se reserva» y con el agente que lo ofrece, si es el mismo para todos.

4.4 **Las preguntas se pliegan:**
- se ve la pregunta y se abre para leer la respuesta;
- «Editar» y «Quitar» pasan a un ⋯ por pregunta;
- al buscar, se abren las que coinciden.

4.5 **Revisar lo leído:**
- arriba de Negocio, una barra dice cuánto queda: «0 de 13 datos revisados»;
- el índice de secciones enseña cuántos faltan en cada una, no un globo;
- «Es correcto» por sección, en la cabecera de cada sección, con la API de hoy (`POST /sections/{section}/confirm`). Dato a dato no entra (D1);
- «Marcar todo como correcto», que pregunta antes. **Cambio en el plan (2026-11-21):** iba con Deshacer, pero la API no sabe «desconfirmar» (confirmar no deja historial) y D1 pide no tocar la API;
- el botón sale siempre que haya algo leído sin revisar y la persona pueda editar Negocio. Hoy, en staging, no salía; el plan averigua por qué.

4.6 **Etiquetas que dicen qué son**: «Zona horaria: Europe/Madrid» y «Moneda de los precios: EUR». Lo leído en inglés dice «Leído en inglés» al lado.

### 5. Comprobación

5.1 Los tests de unidad cubren:
- la agrupación por día (1.2);
- `client_actions` y `delete_blocked` (2.2);
- el resumen de columnas vacías (4.3) y de servicios sin precio (3b.4);
- que «pruebas sin ejecutar» sale una sola vez (3b.3);
- el buscador (4.1).

5.2 Un e2e de Auditoría a 1280 px comprueba que la tabla no se desplaza de lado (`scrollWidth <= clientWidth`). Otro, en la configuración del agente, comprueba que la columna de pruebas no tiene scroll propio. Axe (serious/critical) sobre Auditoría, Negocio y la configuración del agente, en claro y en oscuro.

5.3 El test de aislamiento de la Garantía 1 (encabezado).

5.4 El e2e del marco (`e2e/shell.spec.ts`) sigue verde. Se comprueba en staging, contra el recorrido del estudio, antes de pasar al lote 6.

## Decisiones (owner, 2026-11-21)

- **D1 · Revisar lo leído**: como ya está en la API, **por sección**. «Es correcto» va en la cabecera de cada sección y la barra cuenta datos. Revisar dato a dato, con su endpoint nuevo y su migración, no entra.
- **D2 · La página del agente**: entran la configuración que no se lee (A01) y los avisos repetidos (A04), en §3b. Van a una spec aparte:
  - el esqueleto de 6 s (A05);
  - los filtros de conectores (A06);
  - las conversaciones «En curso» tras 47 h (A07);
  - la tarea escondida en el Resumen de la ficha (F01).
- **D3 · Qué es un acceso en Auditoría**: iniciar sesión, cerrar sesión, renovar la sesión y los intentos fallidos. Quedan en «Todo, con accesos»; lo demás sale en «Solo cambios».

## Fuera de alcance

- El Panel, Consumo, la campana y el dinero: son de las specs 071 y 072.
- El esqueleto del agente, sus conectores, el estado de sus conversaciones y el Resumen de la ficha (A05, A06, A07, F01): van a otra spec (D2).
- Clientes en el teléfono: hoy esconde el saldo y el menú ⋯. Es del lote 6 (cierre).
- Qué se borra al eliminar un cliente: es de la spec 062.
- La tipografía y la escala: son de la spec 068 (base visual).
- La app móvil.
