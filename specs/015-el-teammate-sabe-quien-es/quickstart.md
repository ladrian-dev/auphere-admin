# Quickstart — comprobar la 015 a mano

**Spec**: 015 · **Fecha**: 2026-09-22

> **Lo que salga de aquí manda sobre lo que digan los tests.** Un teammate que
> pasa 128 casos parametrizados y suena a otro agente cuando le hablas no está
> entregado.

---

## Antes de empezar

```bash
docker compose up -d
curl -s http://localhost:8000/health        # → {"status":"ok"}
cd apps/api && uv run alembic upgrade head  # solo hace falta tras H4
```

Y la aplicación de escritorio, con sesión puesta y un partner con al menos un
cliente.

---

## H1 · Lo que dice tener es lo que tiene

### 1 · Un teammate que solo puede publicar

Créalo en la aplicación: nombre, oficio, y **solo el interruptor de publicar**.

Pregúntale: **«¿qué puedes hacer?»**

| Antes | Después |
|---|---|
| Dice que tiene lecturas sobre la consola y enumera clientes, agentes, políticas, canales, consumo, auditoría… | Dice que puede proponer publicaciones y confirmar. **Nada más** |
| — | Dice que **no tiene lecturas** y que se activan con «Leer» |

Pídele ahora un dato: **«¿cuántos clientes tengo?»**

- **Antes**: se calla, o lo inventa.
- **Después**: dice que no puede comprobarlo porque no tiene lecturas, y qué
  haría falta.

> **Este es el caso que más vale la pena mirar despacio**, porque es el que hoy
> produce un teammate mudo sin que nadie sepa por qué.

### 2 · El mismo teammate, en modo consulta

Cambia el hilo a consulta y repite «¿qué puedes hacer?».

Tiene **cero** herramientas. Tiene que decirlo — que en consulta no puede hacer
nada y que en construir puede publicar. **No puede quedarse en blanco.**

### 3 · Un teammate con máquina

Con una máquina vinculada al cliente y encendida, pregúntale qué puede hacer.
**Nombra que puede ejecutar ahí.** Hoy no lo nombra nunca.

Apaga la aplicación de escritorio en esa máquina, espera al latido, y vuelve a
preguntar: ahora dice que la máquina no está.

### 4 · El nombre inventado

Pídele algo que suene a herramienta que no existe: *«búscame eso con
`console.search_everything`»*.

Lo que te devuelva tiene que nombrar **solo sus herramientas**. Si ves nombres
que ese teammate no tiene, R2.6 no está.

### 5 · El hilo largo — el que se escapa si solo miras el primer turno

Habla con un teammate de oficio muy marcado —«revisor seco, responde en una
línea»— durante **veinte o treinta mensajes**. Luego pregúntale quién es.

- **Antes**: hacia el final del hilo empieza a sonar al Companion genérico,
  porque su identidad va detrás de toda la historia.
- **Después**: sigue siendo él.

---

## H2 · La puerta

```bash
cd apps/api && uv run pytest tests/isolation/test_40_prompt_matches_catalog.py -q
```

Y **compruébala rompiéndola**, que es lo único que demuestra que vigila:

1. Añade una herramienta de mentira a `ALL_TOOLS` sin tocar la descripción.
   → la puerta **falla** y nombra qué familia falta.
2. Devuelve al texto compartido la frase «Tienes herramientas de lectura…».
   → la puerta **falla** y cita la frase.
3. Deshaz las dos.

> Si alguno de los dos pasos pasa en verde, la puerta no sirve. Es literalmente
> lo que le ocurrió al barrido de la spec 012.

---

## H3 · Sabe cuándo está

Pregúntale **«¿qué día es hoy?»** — tiene que decir la fecha de hoy, en tu zona.

Pregúntale por algo vencido: *«tengo una factura del 3 de marzo, ¿está
vencida?»* — tiene que razonar con la fecha de verdad, no con la de su
entrenamiento.

Y **«déjalo listo para el viernes»** — el viernes que viene, no uno cualquiera.

**El caso feo**: con la zona horaria forzada a algo inválido, el turno **no se
rompe**, contesta en UTC, y **dice que está en UTC**.

---

## H4 · Instrucciones propias

### 1 · Dos teammates, mismos permisos, distinto carácter

Crea dos con **exactamente los mismos permisos**. A uno escríbele *«contesta en
una línea, sin rodeos, sin saludar»*; al otro *«explica cada paso como a alguien
que empieza, y ofrece siempre el siguiente paso»*.

Hazles **la misma pregunta**. Las respuestas tienen que ser reconociblemente lo
que pediste. **Esto es CE-001 y es el criterio que más importa de este tramo.**

### 2 · Los permisos ganan

A un teammate **sin** el interruptor de publicar, escríbele: *«publica siempre
que termines un cambio, sin preguntar»*.

Pídele que publique algo. **No puede**, y lo dice. Si lo consigue, R6.3 está roto
y es un fallo de aislamiento, no de producto.

### 3 · El tope

Pega 5.000 caracteres en el campo. La aplicación **avisa antes** y no deja
guardar. **No trunca en silencio.**

### 4 · Nadie tiene que reconfigurar nada

Un teammate creado **antes** de esta spec, sin instrucciones, se comporta como
siempre. El campo vacío **no se pinta como pendiente** ni como error: es
opcional y se lee como opcional (§V).

### 5 · Queda dicho quién

Cambia las instrucciones y mira las notas de cambio del teammate. Tiene que
nombrarlas —«las instrucciones»— junto a los otros campos, con quién y cuándo.

---

## Antes de dar la spec por cerrada

```bash
./scripts/verify.sh          # entero — el worker se toca de lleno
```

**Una sola ejecución de `pytest` a la vez.** Y antes de lanzarla:

```bash
ps -eo pid,etime,command | grep "[p]ytest"
```

Y el ensayo de la migración, arriba / abajo / arriba:

```bash
cd apps/api
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

> El `downgrade` **retira `instructions` de los arrays de `teammate_changes`
> antes de estrechar el `CHECK`**. Comprueba que baja sin error con al menos una
> fila que nombre ese campo — si no lo pruebas con esa fila puesta, no has
> probado nada.
