# Quickstart de validación — spec 017

Cómo demostrar cada iteración. Todo en local salvo lo que dependa de Meta
(staging). El partner de prueba es `demo-audit` con el cliente
`panaderia-la-espiga` (plantilla de panadería) y, para «sin sector», un
cliente con agente escrito a mano.

## Requisitos

- Stack local: `preview_start api` y `preview_start console` (o Docker +
  uvicorn :8000 + `pnpm --dir apps/console dev` :3110); ver `apps/console/README.md`.
- `NODE_OPTIONS=--experimental-require-module` para Vitest con Node 22.11;
  Storybook con Node 24 (`~/.nvm/versions/node/v24.14.0/bin`).
- Cuatro sesiones para probar roles: owner, builder, analyst, billing
  (`seed_console_memberships.py --set-password`).

## Por iteración

Cada iteración cierra con los cuatro pasos:

1. **Prototipo aprobado**: story en `packages/ui/src/stories/prototypes/`,
   captura y visto bueno del owner en `evidence/iteracion-N.md`.
2. **Suites**: `pnpm --dir packages/ui test`, `pnpm --dir apps/console test`,
   `cd apps/api && uv run pytest tests/integration tests/unit -k console`,
   `tests/isolation` completo.
3. **E2E axe + overflow**: `cd apps/console && E2E_EMAIL=… E2E_PASSWORD=… ./node_modules/.bin/playwright test`
   (ES y EN, 360 y 1 920 px, +30 % de texto).
4. **Paridad**: la tabla de la pantalla en `parity.md` con el 100 % de las filas
   resueltas; recorrido completo crear cliente → cupo → agente → integraciones →
   operativo en local, y en staging tras el despliegue.

## Iteración 1 · Ficha (R1–R3)

- Abrir `/clients/panaderia-la-espiga` como builder: cabecera con cuatro pasos,
  «canal» pendiente, botón «Conectar un canal» → Canales; cupo «x de y créditos».
- Como analyst: Observar completo, Configurar y Conectar en solo lectura, sin «Más».
- Como owner con el cliente activo: «Más» ofrece Pausar y Archivar, no Eliminar;
  tras archivar, ofrece Reactivar y Eliminar.
- A 1 024 px: tres grupos completos sin scroll horizontal; a 375 px: selector.
- Guardar un cambio en Ajustes → barra de borrador en todas las pestañas; «Ver
  diferencias» muestra «Horario: Atiende siempre → L–V 9–18»; «Publicar» → barra
  fuera, versión nueva activa en Agente. Como analyst: la barra dice quién puede.
- `/clients/panaderia-la-espiga/tools` redirige a `/capabilities`.

## Iteración 2 · Capacidades e Integraciones (R4–R5)

- Panadería: solo grupos y capacidades de su sector y comunes; contador «n de
  otros sectores · Ver todas»; ninguna etiqueta `#barbershop` visible.
- Un clic activa «Reservas» → barra de borrador; toast confirma; sin botón Guardar.
- Capacidad que necesita WooCommerce: «Necesita WooCommerce · Conectar» y no se
  puede activar (409 si se fuerza por API).
- Ningún «Requiere aprobación»; `PUT` con `needs_approval` → 422.
- Cliente sin sector: todo el catálogo y la línea que lo dice.
- Conectar WooCommerce arriba → las capacidades de Pedidos pasan a utilizables.

## Iteración 3 · Consumo (R6)

- Saldo en créditos con «≈ USD · ≈ mensajes (estimación general)» en un partner
  sin historial y «(media de 30 días)» en uno con consumo.
- Reparto: barra por cliente; «Ajustar» → editar tope / mover en un diálogo;
  mover 1 000 créditos y volver; suma de topes intacta si el segundo falla.
- Tabla sin `llm.*`; `/usage/alerts` redirige a `/usage#alerts` y las alertas se
  editan plegadas dentro de Saldo.
- Saldo ilegible (apagar la API de cartera): Saldo dice que no pudo, el resto sigue.

## Iteración 4 · Alta (R7)

- Contar: 4 clics + 1 campo + 2 de plantilla hasta el agente publicado.
- Paso 2 sin preselección; ningún campo antes de elegir; obligatorios primero.
- Fin en la ficha con «Conectar un canal» señalado. Sin paso «Canal».

## Iteración 5 · Inicio y lista (R8–R9)

- Partner nuevo: una sola tarjeta; con plan sin teammates no aparece «Tu puesto».
- Usar el Playground **no** marca «Conecta un canal» ni «Recibe la primera conversación».
- Lista con tres clientes (listo, sin canal, sin cupo): puntos y barra por fila;
  clic en cualquier parte abre la ficha; sin columnas de referencia ni zona horaria.

## Iteración 6 · Ajustes del agente (R10)

- Sin franjas: Horario plegado con «Atiende siempre»; selector de zona horaria
  con ciudades; idiomas con nombres; contador de caracteres; Guardar siempre visible.

## Iteración 7 · Transversal (R11)

- Tab hasta un `HelpHint` y Enter: se abre; `/ayuda` lista los términos.
- Playground: turno fallido = «Error» con causa y reintento; hilo «Conversación del …».
- Ajustes del cliente: referencia copiable en Datos; destructivas en Zona de peligro.
- Facturación: cambiar el correo; Auditoría: filtrar por «Clientes».
- `grep -rn "font-mono" apps/console/src` solo en identificadores, código y `Kbd`.
