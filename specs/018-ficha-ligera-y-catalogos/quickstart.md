# Quickstart · cómo se comprueba que esto funciona

Recorridos sobre la aplicación real, no sobre el código. Cada uno demuestra una
historia de la spec y se puede hacer en cinco minutos.

## Antes de empezar

```bash
docker compose up -d
```

Luego, desde la consola de Claude Code: `preview_start api` y `preview_start
console`. Entrar en `http://localhost:3110` con el owner del partner de prueba
`demo-audit`. El cliente sembrado es `panaderia-la-espiga`.

Para Storybook (los prototipos de cada iteración) hace falta Node ≥ 22.12:

```bash
nvm use 24.14.0
```

---

## Iteración 1 · El Resumen contesta (Historias 1, 2 y 5)

1. Abrir `/clients/panaderia-la-espiga`.
2. **Esperado**: cuatro bloques que contestan si atiende, cuánto consume y
   cuánto le queda, cómo va la conversación y qué tiene conectado. Cada cifra
   lleva a su detalle con un clic.
3. Cambiar el nombre del cliente desde el Resumen y guardar.
   **Esperado**: se guarda, y **no** aparece la barra de «cambios sin publicar»
   —cambiar el nombre del negocio no es cambiar lo que el agente hace—.
4. Abrir `/clients/panaderia-la-espiga/settings`.
   **Esperado**: acaba en la ficha, no en un 404.
5. Abrir `/clients/panaderia-la-espiga/agent/settings`.
   **Esperado**: acaba en `/agent`, con los ajustes dentro.
6. Contar las pestañas: **nueve**.
7. Parar la API (`preview_stop api`) y recargar la ficha.
   **Esperado**: los bloques dicen que no se pudo leer y ofrecen reintentar;
   ninguno enseña un cero que parezca una caída.

## Iteración 2 · Los catálogos se navegan (Historias 3 y 4)

1. Abrir `/clients/panaderia-la-espiga/capabilities`.
   **Esperado**: se llama **Habilidades**. Buscador, pestañas para ver lo activo
   o todo, filtro por categoría, y grupos.
2. Escribir «cita» en el buscador.
   **Esperado**: la lista se reduce y el contador lo dice.
3. Filtrar por una categoría que no deje nada.
   **Esperado**: dice con qué se filtró y ofrece quitarlo — y es un mensaje
   distinto del de un catálogo vacío.
4. Copiar la dirección de la página con el filtro puesto, abrirla en otra
   pestaña y volver atrás.
   **Esperado**: se ve lo mismo, y volver atrás hace lo esperado.
5. Repetir 1–4 en `/integrations` (ahora **Conectores**) y en `/channels`.
   **Esperado**: el buscador, las pestañas y el filtro están en el mismo sitio y
   se llaman igual en los tres.
6. Buscar en toda la consola «Capacidades» e «Integraciones».
   **Esperado**: no aparecen.

## Iteración 3 · Las palabras se explican (Historia 4)

1. Abrir `/clients/panaderia-la-espiga/knowledge`.
   **Esperado**: la cabecera dice que eso lo lee el agente de **ese** cliente
   para responder a sus clientes finales.
2. Abrir `/knowledge` (Guía del partner).
   **Esperado**: la cabecera dice que eso lo lee el asistente de la consola y
   que el agente de un cliente **no** lo ve.
3. Dárselo a leer a alguien que no conozca el producto y preguntarle cuál
   alimenta al agente. **Esperado**: acierta (CE-005).

---

## Las suites que tienen que estar en verde

```bash
pnpm --dir apps/console test
pnpm --dir apps/console typecheck && pnpm --dir apps/console lint
```

```bash
cd apps/api && uv run pytest -x --tb=short
```

Accesibilidad y recorridos (las credenciales las pone quien ejecuta):

```bash
cd apps/console && pnpm exec playwright test a11y.spec.ts record.spec.ts
```

**Criterio**: cero violaciones serias o críticas de axe, sin desbordes a 360 px
ni a 1920 px, con el texto inflado al 130 %, en español y en inglés.

## Lo que no se puede comprobar en local

Nada de esta spec. No toca WhatsApp, no toca pagos y no toca conectores reales:
solo mueve lecturas que ya existen y cambia cómo se navega.
