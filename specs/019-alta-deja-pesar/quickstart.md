# Quickstart — el alta deja de pesar

Cómo se comprueba que esta spec hizo lo que dice. Los criterios de éxito que un
test puede medir van en su tarea; aquí están **los que hay que mirar con los
ojos**, y el recorrido completo de cada iteración.

## Antes de empezar

```bash
docker compose up -d && cd apps/api && uv run alembic upgrade head
```

`preview_start api` · `preview_start console` → `http://localhost:3110`.
Partner sembrado: `demo-audit`.

---

## Iteración 1 · el alta en tres pasos

### CE-001 · cuatro campos, no veintitrés

1. Abre **Nuevo cliente**.
2. Elige **Barbería / Peluquería**.
3. Cuenta los campos del paso siguiente.

**Pasa si**: hay cuatro — nombre, zona horaria, dirección y horario. Ni uno más.
Antes de esta spec, la pantalla enseñaba 23 con la plantilla marcada por defecto.

Repítelo con **Cobranza** y con **Clínica estética**. Medido sobre la consola en
marcha el 2026-09-29, al cerrar la iteración:

| Plantilla | Campos en el paso 2 | Cuáles |
|---|---|---|
| Barbería / Peluquería | **4** | nombre, zona horaria, dirección, horario |
| Cobranza | **3** | nombre, zona horaria, teléfonos de administradores |
| Clínica estética | **9** | los cuatro de arriba + titular, clínica y teléfono de referencia, Instagram y teléfono de recepción |

Dos correcciones a lo que este documento decía antes, y las dos por haberlo
medido en vez de suponerlo:

- **Cobranza son tres, no dos.** Exige la lista blanca de administradores, y no
  es un capricho: sin ella el agente no contesta a nadie.
- **La clínica estética son nueve, no catorce.** T036 dejó de exigir los cinco
  que el owner sacó del alta, porque el prompt dejó de afirmarlos.

### CE-002 · tres pasos, y ninguno que sobre

Recorre el alta contando pasos. **Pasa si** son tres y ninguno pregunta por el
canal.

### CE-003 · nadie termina con una plantilla que no eligió

Abre el alta y pulsa continuar sin tocar nada. **Pasa si** no deja pasar.

### CE-004 · alguien de fuera encuentra su plantilla *(a mano, no automatizable)*

**Esto no lo puede comprobar un test y por eso está aquí.** Pídeselo a alguien
que no conozca el producto:

> «Vas a dar de alta un restaurante. Encuéntralo.»

**Pasa si** lo encuentra sin recorrer las trece y sin preguntarte nada. Anota en
la evidencia **qué dijo en voz alta** mientras lo hacía: es el dato que ningún
número recoge.

---

## Iteración 2 · lo que el alta dejó de pedir

1. Crea un cliente sin rellenar dirección ni horario.
2. Entra en su ficha.

**Pasa si**: la tarjeta «Pasos para activar tu agente» enseña un paso más,
**Datos del negocio**, con su barra a medias. Rellénalo y comprueba que el paso
**desaparece entero** — la tarjeta no puede crecer para siempre.

---

## Iteración 3 · el Companion redacta

### CE-005 · se distingue lo propuesto de lo escrito

1. En el paso 1, escribe: «barbería en Madrid, cuatro sillas, abre sábados».
2. Mira el formulario.

**Pasa si**: hay una propuesta de plantilla con su porqué, los campos llegan
rellenos y **se ve cuáles los puso la máquina**. Cambia uno: debe dejar de estar
marcado como propuesto.

### CE-006 · sin Companion, el alta se recorre igual

Apaga el Companion para el partner y repite el alta entera.

**Pasa si**: la caja **no aparece** —ni apagada, ni con un texto explicando lo
que no tienes— y el alta se completa sin ella.

---

## Al cerrar cualquier iteración

### CE-007 · ninguna dirección vieja responde «no existe»

```bash
cd apps/console && pnpm exec playwright test --project=desktop --no-deps
```

Y a mano, las que estaban en correos y marcadores: `/clients/new`.

### Las suites

```bash
cd apps/console && pnpm test && pnpm lint && pnpm typecheck
cd packages/ui && pnpm test && pnpm lint && pnpm typecheck
./scripts/verify.sh locks
```
