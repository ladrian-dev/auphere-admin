# Quickstart — cómo se valida la spec 010

Guía de ejecución y validación. **No** lleva código de implementación: dice qué
correr, qué mirar y qué tiene que pasar.

## Requisitos previos

```bash
# dependencias del monorepo
pnpm install

# la plataforma, para los recorridos con datos reales
docker compose up -d
curl -s http://localhost:8000/health   # → {"status":"ok"}
```

La aplicación apunta a **producción** salvo que se le diga otra cosa. Para
validar contra local, hay que declararlo **siempre**:

```bash
cd apps/desktop
AUPHERE_CONSOLE_URL=http://localhost:3000 AUPHERE_API_URL=http://localhost:8000 pnpm start
```

> La primera línea del arranque dice contra qué entorno está hablando. Si esa
> línea no coincide con lo que se quiere probar, todo lo demás es ruido: probar
> contra el entorno equivocado tiene el mismo síntoma que un fallo de código.

## Suites

```bash
# lo que corre la tubería, entero
./scripts/verify.sh

# durante el desarrollo
cd apps/desktop && pnpm test          # unidad y componente
cd packages/ui && pnpm test           # incluye el test de contraste de pares
./scripts/verify.sh js                # consola, panel, @nexus/ui, companion-ui, escritorio

# accesibilidad y humo del binario (spec 010)
cd apps/desktop && pnpm test:a11y     # axe sobre las pantallas
cd apps/desktop && pnpm test:smoke    # arranque del binario empaquetado
```

**«Verde en local» y «verde en la tubería» no son lo mismo** si cada uno corre una
lista distinta. Antes de fusionar, `./scripts/verify.sh` entero. Lo que se olvida
no son las pruebas de la API: son el worker, el tipado estricto, el paquete
compartido y la compilación de la consola.

## Recorridos de validación, por historia

### P1 · Armazón (R1, R2)

1. Abrir la aplicación. **Mirar**: no hay destello; la franja superior es propia
   y los controles del sistema están dentro; hay una sola lista lateral.
2. Arrastrar la ventana **por la franja**: se mueve. Arrastrar **dentro del
   panel**: no se mueve.
3. Ir a «Consumo»: la página aparece **dentro del panel**, sin segunda
   navegación, y la lista lateral la marca.
4. Navegar dentro de la consola (por ejemplo de consumo a facturación): la lista
   lateral sigue el movimiento.
5. Volver a un teammate y de nuevo a la sección: **no se recarga**.
6. `⌘B`, `⌘[`, `⌘]`, `⌘K`, `⌘,`: cada uno hace lo que dice el menú.
7. Cerrar y reabrir: vuelve al mismo sitio y tamaño.
8. **Mirar la tipografía**: una sola familia en toda la ventana, incluida la
   sección de administrar.

### P2 · Estados honestos (R3, R4)

| Cómo se provoca | Qué tiene que pasar |
|---|---|
| Apagar la red **antes** de abrir | Armazón pintado, «sin conexión», reintento. **No** aparece el inicio de sesión |
| Apagar la red **con la sesión abierta** | «Sin conexión», el borrador se conserva, vuelve solo al reconectar |
| Apuntar a una API que devuelve error al abrir un hilo | Error con motivo y reintento; **nunca** «hilo vacío» |
| Detener lo que ejecuta en la máquina | El puesto dice `reconectando` **con causa** «falta el ejecutor» y qué hacer |
| Cerrar la ventana con una decisión pendiente | La aplicación sigue viva y avisa; «Salir» advierte |

### P3 · Avisos y contador (R5, R6)

1. Provocar un fallo al decidir: **se dice**, junto a la tarjeta.
2. Con dos decisiones esperando, comparar los **cuatro** números: coinciden.
   Decidir una: bajan los cuatro.
3. Con la ventana enfocada, provocar una decisión nueva: **no** hay aviso del
   sistema; se ve dentro.
4. Sin foco: llega aviso con **motivo**, sin contenido sensible; al pulsarlo, la
   ventana vuelve al frente con la tarjeta enfocada.
5. Simular versión nueva: se anuncia; con trabajo vivo, **no** se instala y lo
   dice.

### P4 · Primer arranque (R7, R8)

Con una cuenta nueva y la máquina sin emparejar, **cronometrar**:

1. Abrir → «Entrar» → navegador → volver: la ventana se reconoce y **pasa al
   frente**.
2. Cancelar en el navegador: la aplicación lo dice y deja reintentar.
3. Puesta en marcha: emparejar **sin salir de la aplicación** — pedir el código y
   teclearlo, todo visible y alcanzable con teclado.
4. Crear el primer teammate y enviarle algo. **Objetivo: ≤10 minutos** (CE-001).

### P5 · Llevar a la acción (R9)

| Caso | Qué tiene que ofrecer |
|---|---|
| Plan sin teammates | Se dice **antes** del formulario, con «Ver planes» |
| Sin permiso para contratar | A quién pedírselo; **sin** botón que no puede usar |
| Pagar | La ventana dice que se abrió el navegador y espera; al volver, plan y consumo al día **sin reiniciar** |
| Consumo al 80 % | Aviso con fecha de reinicio |
| Consumo agotado sin saldo | **Una sola** explicación, con opciones; al resolverlo, lo pausado se reanuda |

### P6 · Decidir (R10)

1. En Pendientes: qué se hará, dónde, desde cuándo, si se deshace — sin abrir nada.
2. Teclado: aprobar, rechazar, y aprobar siempre donde aplique.
3. Pulsar en el instante en que aparece la tarjeta: **no decide**.
4. Rol sin permiso: a quién pedírselo, y el hilo sigue accesible.

### Ubicuos (R11, R12)

- Recorrer cada pantalla **solo con teclado**, incluido el puesto (F6).
- `pnpm test:a11y`: cero incidencias graves o críticas.
- Zoom al 200 %: nada inalcanzable.
- Cambiar el idioma de la cuenta: menús, diálogos del sistema y avisos cambian.
- Cadena alemana larga en nombre de cliente y de teammate: no desborda.

## Antes de dar la spec por terminada

1. `./scripts/verify.sh` entero, en verde.
2. Los cuatro gates de UI del workspace: estados, accesibilidad, responsive y
   tokens.
3. Documentos vivos actualizados **en el mismo commit**:
   `docs/desktop-workstation.md`, `docs/desktop-teammates.md` y
   `docs/bugs-app-escritorio-2026-09-15.md` (cerrar los fallos que esta spec
   resuelve y corregir los estados desfasados).
4. Recorridos de evidencia de la spec 003 actualizados: cambian la navegación y
   las etiquetas; uno de ellos ya está roto hoy.
5. Un recorrido con el **binario empaquetado y firmado**: es donde aparecieron
   los fallos que no se ven en desarrollo.
