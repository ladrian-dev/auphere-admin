# Quickstart — cómo se comprueba que la 013 funciona

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Fecha**: 2026-09-20

Lo que hay que poder hacer para decir que cada historia está entregada. Sirve
igual para verificar a mano y para saber qué automatizar.

## Antes de empezar

El entorno es el mismo que `docs/prueba-manual-teammate-en-la-maquina.md` §1 y
§2: Postgres y Redis arriba, la API corriendo, la consola en el 3110, y los
teammates sembrados. Para la Historia 3 hace falta además máquina emparejada y
directorio declarado (§4 a §6 de ese documento).

**Aviso del §0 de ese documento, que sigue valiendo**: si el id del modelo no
está en el catálogo Sol/Terra/Luna, el turno devuelve 409 antes de llamar a
nadie. Es lo primero que suele fallar.

---

## H1 · El hilo recuerda la conversación entera

```
1. Escribirle algo a un teammate y esperar la respuesta.
2. Cerrar la aplicación del todo.
3. Abrirla y volver al mismo hilo.
```

**Se cumple si** se ve lo que escribiste **y** lo que contestó, en orden.
**Hoy falla**: solo está la respuesta.

Y la frontera, que es lo que de verdad importa comprobar:

```
Con la sesión de otra persona del mismo partner, pedir los runs de ese hilo.
```

**Se cumple si** responde como si no existiera. No «prohibido»: **no existe**.

---

## H2 · El texto se pinta como lo que es

Pedirle al teammate algo que le haga responder con las tres formas:

> «Dame los pasos en una lista numerada, una tabla con tres filas, y un ejemplo
> en Python.»

**Se cumple si** la lista es una lista, la tabla es una tabla y el código está en
un bloque con su botón de copiar. **Y si lo copiado es exactamente el código**,
sin el resto del mensaje.

Las dos pruebas que se olvidan:

- **Mientras llega.** Mirar durante el streaming: un bloque de código a medio
  llegar no debe romper lo de abajo, y el texto no debe parpadear entre formatos.
  Una tabla a medias sí cambia de aspecto al completarse — eso es esperado y está
  dicho en research §5.
- **Contenido hostil.** Un mensaje con `<img src="http://…">` o con un enlace
  `javascript:`: no se carga nada de fuera y no pasa nada al pulsar.

---

## H3 · Se ve lo que el comando hizo

```
1. Pedirle al teammate que ejecute algo que falle: `make build` sobre el
   Makefile de la prueba manual, que sale con código 1.
2. Aprobar.
```

**Se cumple si** en pantalla aparece el motivo del fallo —el que `make` escribe
por el flujo de error— y no solo «salió con código 1».

Y las dos que hacen que sea legítimo:

```
3. Consultar la base de datos: qué se ejecutó, dónde y cómo acabó, sí;
   lo que imprimió, en ninguna tabla.
4. Volver al hilo pasados quince minutos.
```

**Se cumple si** en el paso 3 no aparece el texto en ningún sitio, y en el 4 la
pantalla **dice** que la salida no se conserva en lugar de dejar un hueco.

La consulta del paso 3 está en `docs/prueba-manual-teammate-en-la-maquina.md` §9.

---

## H4 · Una conversación por asunto

```
1. Hablar con un teammate.
2. Empezar una conversación nueva con el mismo.
3. Escribir algo distinto.
4. Volver a la primera.
```

**Se cumple si** las dos están enteras, se distinguen sin abrirlas, y al cerrar y
volver a abrir la aplicación aterrizas en la última en la que trabajaste.

---

## H5 · Corregir el tiro

```
Editar el último mensaje propio y reenviarlo. Copiar una respuesta.
Con un turno en marcha, intentar editar.
```

**Se cumple si** el turno se rehace desde ahí sin dejar dos versiones mezcladas,
lo copiado es el texto tal como se escribió, y con un turno vivo **se dice por
qué no se puede** en vez de que el control falle al pulsar.

---

## H6 · Al abrir, se puede escribir

```
Abrir la aplicación con al menos un teammate.
Y otra vez, con ninguno.
```

**Se cumple si** en el primer caso hay dónde escribir y se ve a quién; en el
segundo lo primero es crear uno **y no hay un composer que no lleve a ningún
sitio**. Con la máquina apagada se tiene que poder conversar igual.

---

## H7 · Encontrar lo que se dijo

```
Buscar un término que aparezca en una conversación de hace días.
Buscar algo que no exista.
```

**Se cumple si** lo encuentra y salta ahí, y si lo segundo dice que no hay nada
de forma distinguible de estar cargando.

---

## Las puertas antes de decir que está

En este orden, y ninguna se salta:

```bash
./scripts/verify.sh lint    # ruff + mypy --strict
cd apps/api && uv run pytest tests/ -q -p no:randomly
./scripts/verify.sh js      # consola, panel, @nexus/ui, companion-ui, escritorio
```

**`verify.sh js` entero, no solo la suite de escritorio.** Esta spec toca
`packages/companion-ui`, que comparten la aplicación y la consola: es
exactamente el paquete que este repositorio olvida y que ha roto la tubería dos
veces.

Y los cuatro gates de interfaz del CLAUDE.md del workspace antes de dar por
cerrada cualquier pantalla: estados, accesibilidad, responsive y tokens.
