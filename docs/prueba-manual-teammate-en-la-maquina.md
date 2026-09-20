# Probar a mano que un teammate trabaja en tu máquina

> **Qué prueba esto.** El camino entero de la spec 003 sobre la superficie `3a`:
> la máquina se empareja, declara un directorio, el teammate ve la herramienta,
> pide permiso, ejecuta y **lee lo que salió**. Es lo que arreglaron
> `.specify/bugs/el-teammate-no-alcanza-la-maquina/` (D1-D4) y
> `.specify/bugs/el-cliente-no-es-un-argumento/`.
>
> **Nunca se había recorrido de punta a punta.** Los tests cubren cada tramo por
> separado; esto es la primera vez que se juntan.
>
> Escrito el 2026-09-20. Si algo de lo de aquí deja de ser verdad, este
> documento va en el mismo commit que lo cambió.

## 0 · Lo que hace falta antes de empezar

| | Qué | Cómo se comprueba |
|---|---|---|
| a | Docker con Postgres y Redis | `docker compose ps` — `nexus-postgres` y `nexus-redis` en `healthy` |
| b | Una clave de LLM real en `apps/api/.env` | Sin ella el turno responde 409 o falla al llamar al modelo |
| c | `pnpm install` hecho en la raíz | La app y la consola comparten el workspace |
| d | Node y Python del repo | `uv` para la API, `pnpm` para lo demás |

**Sobre la clave del modelo.** `llm_companion_model` vale `openai/gpt-5.6-sol`
por defecto y el turno exige que el id esté en el catálogo `Sol|Terra|Luna`
(`_require_catalog_model`). Si tu clave es de otro proveedor, cambia
`NEXUS_LLM_COMPANION_MODEL` a un id del catálogo que tu proxy sepa resolver, o
el turno devuelve `409` antes de llamar a nadie. **Esto es lo primero que suele
fallar, y el mensaje no lo dice claro.**

---

## 1 · Levantar la plataforma

```bash
cd /Users/lmatos/Workspace/nexus
docker compose up -d
cd apps/api && uv run alembic upgrade head        # tiene que llegar a 0123
uv run uvicorn nexus_api.main:app --reload --port 8000
```

Comprobación: `curl -s localhost:8000/health` → `{"status":"ok"}`.

La migración **0123** es la que este arreglo añadió. Si `alembic upgrade head`
no la nombra, el subdirectorio no viajará y el paso 7 correrá en la raíz.

En otra terminal, la consola:

```bash
cd apps/console && pnpm dev          # http://localhost:3110
```

## 2 · Sembrar partner, cliente y teammates

```bash
cd apps/api
uv run python scripts/dev_seed_console_volume.py --clients 2 --conversations 10 --usage-rows 50
uv run python scripts/seed_teammates_dev.py --partner-slug demo
```

El segundo deja dos teammates. **El que sirve para esto es «Nilo»**, que es el
único sembrado con `local_exec=True`; «Sofía» no lo tiene y **no debe** ver la
herramienta — eso es parte de lo que se prueba (paso 8).

## 3 · Construir y arrancar la app de escritorio

```bash
cd /Users/lmatos/Workspace/nexus
pnpm --filter @nexus/desktop build
pnpm --filter @nexus/desktop start
```

Apúntala a tu API local con las variables que use tu entorno (`NEXUS_API_BASE`
/ `NEXUS_CONSOLE_BASE` hacia `localhost:8000` y `localhost:3110`). La línea de
arranque de la aplicación **dice a qué consola y a qué API apunta** — léela
antes de seguir; si apunta a producción, para aquí.

## 4 · Entrar y emparejar

1. En la app, entrar por el navegador (loopback + PKCE, spec 009).
2. Emparejar la máquina: pedir el código de 8 símbolos en la consola
   (`/workstation`) y teclearlo en la app.

> Este paso es el que la evaluación `maquina-sin-emparejar` propone retirar. Hoy
> sigue haciendo falta.

**Comprobación:** en la consola, `/workstation` lista tu máquina como presente.
La presencia caduca a los 30 s sin latido: si la app está cerrada, sale ausente,
y eso es correcto.

## 5 · Declarar el directorio del cliente

En la app, pie de la barra lateral → **Declarar directorios**. Elige una carpeta
real para el cliente sembrado. Crea algo dentro para tener con qué trabajar:

```bash
mkdir -p ~/pruebas-auphere/boreal/analitica
cd ~/pruebas-auphere/boreal
printf 'print("hola desde el teammate")\n' > analitica/saludo.py
printf 'build:\n\t@echo "compilando"; exit 1\n' > Makefile
```

**Sin directorio declarado no hay dónde ejecutar** y el trabajo se queda en cola
—es una espera diseñada (002-R7.5), no un error—.

## 6 · Permitir un ejecutable

La lista blanca es **del cliente y se toca desde la consola**: es la única capa
que *permite*; el techo del partner y tu preferencia solo restringen.

Consola → cliente → **Puesto de trabajo** → añadir `python` y `make`.

## 7 · La prueba de verdad

En la app, abre el hilo de **Nilo** y pídele algo que exija ejecutar y **leer el
resultado**. Por ejemplo:

> «Corre `make build` en la carpeta de Boreal y dime por qué falla.»

Lo que tiene que pasar, en orden:

| # | Qué esperas ver | Qué defecto cubre |
|---|---|---|
| 1 | Nilo **propone** ejecutar y sale la tarjeta de confirmación con el comando y el cliente | D1 — antes la herramienta no estaba en su catálogo y no podía ni intentarlo |
| 2 | Al aprobar, el comando corre en tu máquina | el puente, que ya existía |
| 3 | **Nilo te dice el motivo del fallo**, no solo «salió con código 1» | D2 — la salida no llegaba al modelo |
| 4 | El motivo viene de **stderr**, que es donde `make` lo escribe | D3 — stderr no se recogía |
| 5 | Si pides algo en `analitica/`, corre **ahí** y no en la raíz | D4 — `cwd_relative` se validaba y se tiraba |

Para el 5, pídele explícitamente: «ejecuta `python saludo.py` dentro de
`analitica`». Si contesta que no encuentra el fichero, D4 no está aplicado —
comprueba que la migración 0123 corrió.

## 8 · Lo que también tiene que fallar

Una prueba que solo confirma lo que esperas no prueba nada. Estas cuatro tienen
que **denegarse**:

| Prueba | Resultado correcto |
|---|---|
| Pedirle lo mismo a **Sofía** | No tiene la herramienta. No debe «intentarlo y fallar»: no la ve |
| Pedir `curl` (fuera de la lista blanca) | Denegado por ejecutable no permitido, y **no** como decisión aprobable: ampliar la lista es un acto de la consola |
| Pedir `make ; rm -rf /` | Denegado por metacaracteres, antes de mirar la lista blanca |
| Cerrar la app, esperar 40 s y mirar la consola | La máquina sale **ausente**, y el catálogo del turno deja de ofrecer la herramienta |

## 9 · Y lo que no se guarda

Esto es §III de la constitución, y conviene verlo con los ojos:

```bash
cd apps/api && uv run python - <<'EOF'
import asyncio, sqlalchemy as sa
from nexus_api.db.base import get_sessionmaker
async def main():
    async with get_sessionmaker()() as s:
        rows = (await s.execute(sa.text(
            "select executable, argv_signature, cwd_relative, outcome, exit_code "
            "from local_executions order by started_at desc limit 5"))).all()
        for r in rows: print(r)
asyncio.run(main())
EOF
```

Tiene que verse **qué se ejecutó, dónde y cómo acabó**, y **nunca lo que el
comando imprimió**. La salida existió, llegó al modelo y no se persistió. Si ves
texto del programa en esa tabla, es un defecto.

---

## Lo que este recorrido NO cubre, y conviene saberlo antes

- **Windows.** La contención tiene su variante con rutas relativas NT (T039 y
  T043 de la spec 001) y **nunca se ha ejecutado**. Este recorrido es macOS.
- **Continuación autónoma.** Tras aprobar, el turno responde y termina. Nilo no
  encadena el paso siguiente solo; cada uno lo pides tú. Es lo que evalúa
  `.specify/assessments/teammate-que-trabaja-en-la-terminal/`.
- **Latencia.** Entre que se aprueba y la máquina lo recoge pasan de 0 a 10 s,
  porque la app sondea. Con varios comandos se nota, y es uno de los números que
  esa misma evaluación tiene que medir antes de decidir si hace falta una sesión
  viva.
- **Sin `cd` entre pasos.** Cada comando es un proceso nuevo: no hay directorio
  que persista, ni variables, ni un servidor levantado de un paso al siguiente.
- **La app publicada (0.1.4) salió de `develop`** y `main` no tiene sus rutas de
  entrada. Esta prueba es con la app **construida en local**, no con la
  instalada; no mezcles las dos.

## Si algo falla

| Síntoma | Dónde mirar primero |
|---|---|
| El turno devuelve 409 nada más empezar | El id del modelo (§0) o el proxy: `_require_catalog_model` y `_require_proxy` |
| Nilo no ve la herramienta | ¿La máquina late? ¿El cliente tiene directorio declarado? Las dos cosas hacen falta |
| Se queda «pendiente» para siempre | La app no está sondeando, o el vínculo con el cliente no tiene `workdir` |
| Ejecuta pero no dice qué pasó | Es D2/D3: comprueba que la app corriendo es la construida hoy |
| Corre en la raíz y no en el subdirectorio | Migración 0123 sin aplicar |
