# Problem Definition: la identidad y el consumo en la aplicación de escritorio

- **Slug**: identidad-y-consumo-en-la-app
- **Created**: 2026-09-09
- **Inputs used**: [`intake.md`](./intake.md) · [`research.md`](./research.md)

> Esta etapa se queda en el **espacio del problema**. Ninguna pantalla, ningún
> endpoint, ningún modelo de datos. Las opciones son de `shape`.

---

## Problem Statement

Un partner que instala la aplicación de escritorio no tiene ningún camino de
producto entre «la acabo de abrir» y «la plataforma sabe quién soy y qué máquina
es ésta»: entrar funciona —la consola se carga y su login basta—, pero **el
emparejamiento de la máquina con la persona no existe** y hoy lo suple un
operador de Auphere ejecutando un script contra la base y haciendo llegar un
secreto por un canal que nadie ha definido. Importa ahora porque todo lo que la
beta 2 construyó —ejecución local contenida, lista blanca, techos, presencia y
auditoría— solo se alcanza a través de esa credencial.

---

## Affected Users & Stakeholders

**Usuarios**

- **La persona del partner que instala la aplicación** (decisión 2: *«¿Quién usa
  la app? Solo el partner»*) — no puede completar la instalación por sí misma. Y
  si trabaja en una máquina compartida con compañeros, ni siquiera está definido
  qué significa «su» dispositivo: `principal_id` se escribe y nunca se lee, así
  que hoy todos ven el dispositivo de todos.
  — [research D-6]
- **La persona del partner que ya está dentro y quiere ver su consumo** — ésta
  **no** está afectada: `/usage` existe, los cinco roles lo pueden leer y el
  consumo de las sesiones locales ya entra en el mismo libro. Se anota aquí para
  cerrarlo: no hay problema que resolver por este lado, solo la tentación de
  crear uno. — [research D-4]

**Interesados**

- **Auphere, como operador** — hoy tiene que intervenir a mano, con acceso
  directo a la base de producción, en cada instalación. Es quien paga el coste de
  no hacer esto y quien decide si se hace.
- **Auphere, como responsable de seguridad** — cualquier camino de emparejamiento
  toca la separación que sostiene la cáscara (Requisito 15.3) y la credencial de
  dispositivo (Requisito 6.3). Tiene poder de veto sobre la forma.
- **El cliente final** — no participa y no debe aparecer: no tiene aplicación
  (decisión 2), y ninguna credencial suya entra en este camino.

---

## Goals

1. **Que un partner complete la instalación sin que nadie de Auphere toque una
   base de datos.** Es el resultado que convierte la beta 2 en algo entregable.
2. **Que la plataforma sepa qué persona reclama qué máquina**, y que esa
   respuesta sea utilizable —no una columna que nadie lee—, de modo que la
   decisión 9 («privado por persona») pueda sostenerse también aquí.
3. **Que una aplicación instalada siga funcionando pasados los primeros días**,
   sin que la caducidad de la credencial obligue a repetir el alta.
4. **Que cerrar sesión y desemparejar una máquina sean dos actos con
   consecuencias dichas**, y que al menos uno de los dos detenga el puente de
   verdad.
5. **Que el consumo se vea sin inventar un segundo contador**: lo que la
   aplicación muestre sale del libro que ya existe.
6. **Que la aplicación no empeore lo que en el navegador funciona.** Si una
   pantalla de la consola se rompe dentro de la cáscara, la promesa del Requisito
   15.1 —«tu ventana al teammate»— deja de ser cierta.

---

## Non-Goals

- **Rehacer el login.** La evidencia dice que el de la consola basta para entrar
  (research D-1). Un flujo de autenticación propio de la aplicación queda fuera.
- **Reimplementar pantallas de la consola.** Requisito 15.1, heredado.
- **Registro / autoservicio de alta de partners.** Depende de la decisión §2.3 de
  la KB, que está abierta. Esta evaluación se acota a lo que es cierto tanto si
  algún día hay autoservicio como si no.
- **Arreglar la revocación de dispositivo que hoy no funciona.** Es un
  incumplimiento del Requisito 6.3 de la spec 001, con su propio camino
  (`/speckit-bug-assess` o converge sobre la 001). Se declara aquí porque
  condiciona la meta 4, no porque se vaya a resolver aquí.
- **Precio, facturación y cuánto cuesta el consumo.** Solo se mira qué **ve** el
  partner.
- **Controlar el escritorio (`3b`), navegador embebido y beta 5.** Fuera en la
  001 y siguen fuera.
- **Abrir superficie de confianza nueva.** Esto trabaja sobre la `0` y sobre el
  tramo de emparejamiento de la `3a`, ambas ya pagadas (§II).

---

## Success Metrics

- **M-1 · Instalaciones completadas sin intervención de operador**: 100 % de las
  altas nuevas. *(Base actual: 0 % — hoy toda alta pasa por
  `scripts/enrol_device_dev.py`.)*
- **M-2 · Acceso de Auphere a la base de producción para dar de alta un
  dispositivo**: cero veces. *(Base actual: una vez por instalación.)*
- **M-3 · Vida útil de una instalación sin repetir el alta**: la aplicación sigue
  operativa indefinidamente mientras la persona conserve acceso. *(Base actual:
  **12 horas** — `DEFAULT_TTL` de la credencial, sin renovación.)*
- **M-4 · Un dispositivo tiene dueño legible**: el 100 % de los dispositivos
  responde a «¿de quién es?» con una consulta, no con una suposición. *(Base
  actual: la columna existe y ninguna consulta la usa.)*
- **M-5 · Contadores de consumo distintos en el producto**: exactamente **uno**.
  *(Base actual: uno. Ésta es una métrica de no-regresión: se cumple hoy y el
  riesgo es romperla.)*
- **M-6 · Pantallas de la consola que funcionan en el navegador y no dentro de la
  cáscara**: cero. *(Base actual: **desconocida** — el riesgo del Embedded Signup
  de Meta está razonado y no medido; research D-2, confianza media.)*
- **M-7 · Cualitativa** — una persona ajena al equipo instala la aplicación
  siguiendo solo lo que la pantalla dice, sin instrucciones nuestras por otro
  canal. *(Base actual: imposible.)*

---

## Cost of Inaction

**La beta 2 no se entrega.** No es una degradación de experiencia: es que las
setenta y tres tareas construidas —contención en macOS, lista blanca por tenant,
techos de reloj y muerte de árboles de procesos, presencia, aprobaciones
durables, auditoría por tenant, aislamiento de sesión y el puente saliente
completo— quedan inalcanzables para cualquiera que no sea nosotros con una
terminal abierta contra la base.

El coste de seguir así tiene además tres formas concretas:

1. **Operativa**: cada instalación exige acceso directo a producción y el envío
   de un secreto por un canal no definido. Eso es un procedimiento que no se
   puede auditar ni delegar, y que empeora cuanto más éxito tenga el producto.
2. **De caducidad**: aunque se acepte el procedimiento manual, la instalación
   muere a las 12 horas. No hay «piloto pequeño» que sobreviva a un fin de
   semana.
3. **De deuda de decisión**: la columna `principal_id` y el `tenant_id` del
   dispositivo son decisiones tomadas por herencia, no por elección. Cuanto más
   tarde se decida de quién es una máquina, más caro sale — si la respuesta
   resulta ser «del partner», toca modelo de datos, RLS y tests de aislamiento de
   la 001.

**El argumento honesto en contra** también es real y `decide` tiene que pesarlo:
con dos o tres partners piloto el procedimiento manual funciona, esto no es el
diferencial del producto, y nadie lo ha pedido desde fuera.

---

## Open Questions

- [NEEDS CLARIFICATION: **¿de quién es un dispositivo — del tenant cliente o del
  partner?** Es la pregunta que decide si esta evaluación toca el modelo de datos
  de la 001. Sin ella no se puede dimensionar nada. — research D-5]
- [NEEDS CLARIFICATION: **¿qué se abre para que la máquina reciba su credencial?**
  Hoy la página cargada no tiene ninguna vía de hablar con la cáscara (sin
  `preload`, `contextIsolation` activo, `sandbox` activo). Toda opción pasa por
  abrir un canal o por evitar necesitarlo, y abrirlo roza el Requisito 15.3. —
  research D-3]
- [NEEDS CLARIFICATION: **¿cuánto dura la credencial de dispositivo y qué la
  renueva?** — research D-7]
- [NEEDS CLARIFICATION: **¿cerrar sesión desempareja la máquina?** Y si no, ¿qué
  la desempareja, sabiendo que hoy archivarla no detiene el puente? — research
  D-7 y dependencia declarada]
- [NEEDS CLARIFICATION: **¿funciona el Embedded Signup de Meta dentro de la
  cáscara?** Spike acotado; decide si M-6 arranca en cero o en uno. — research
  D-2]
- [NEEDS CLARIFICATION: **¿qué ve el partner en una máquina compartida?** La 001
  supuso mono-usuario y la decisión 9 dice lo contrario para los hilos. Las dos
  cosas no pueden ser ciertas a la vez en un puesto compartido. — research D-6]
