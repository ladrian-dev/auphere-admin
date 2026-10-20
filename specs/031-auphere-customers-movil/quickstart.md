# Quickstart: cómo se comprueba que la spec 031 funciona

Esta guía dice qué se ejecuta y qué hay que ver. **No contiene
implementación**: los detalles están en los
[contratos](contracts/) y en el [modelo de datos](data-model.md).

## Requisitos previos

- La pila local con `docker compose up -d`. `curl -s
  http://localhost:8000/health` devuelve `{"status":"ok"}`.
- La semilla de un cliente con Lite y sus tres módulos, una persona de cliente y
  la Bandeja con WhatsApp de pruebas. Son las fixtures de la spec 030
  (`make_client_access`, `add_client_member`, `make_inbox`) y su script de
  semilla.
- Un **segundo cliente del mismo partner**, con su propia persona, para los
  barridos.
- Para la app:
  - Node 24 y pnpm 10;
  - Xcode 26.4 o posterior con un simulador de iOS 26;
  - Android Studio con un emulador de API 36;
  - Maestro 2.x.
- Para ver avisos de verdad hace falta un **dispositivo físico** con un build de
  desarrollo. Los simuladores no reciben APNs reales; el emulador de Android sí
  recibe FCM.

## 1. Lo que corre la tubería

```bash
./scripts/verify.sh
```

Tiene que salir todo en verde, y ahora incluye el paso `mobile`:

- `tsc`, `eslint` y `jest` de `apps/mobile`;
- los tres generadores con `--check`. Si el tipo, el token o el texto
  generados no coinciden con el confirmado, la tubería falla y dice qué archivo
  regenerar.

Lo que más se olvida (CLAUDE.md): **el worker**, porque `test_bootstrap_split`
debe conocer `push-dispatcher`, **`mypy --strict`** y el **`next build`** de la
consola.

## 2. Los seis barridos de aislamiento (R15, CE-006)

```bash
cd apps/api && uv run pytest tests/isolation/ -x -k "phone or push"
```

Esperado: seis archivos en verde, sin `skip`.

| Archivo | Lo que demuestra |
|---|---|
| `test_phone_client_vs_client.py` | Ningún hecho de un cliente produce un aviso en un teléfono del otro, para los tres tipos |
| `test_phone_route_scope.py` | Con la credencial de un teléfono, todas las rutas `/console/lite/*` devuelven solo su cliente y sus módulos |
| `test_phone_revocation.py` | Tras cerrar, quitar o apagar, el teléfono no lee y el reparto lo salta |
| `test_push_payload_no_customer_content.py` | Con teléfonos, mensajes largos, notas y archivos «canario» en los datos, el payload de APNs y FCM solo lleva los campos de R9.2 y dentro de sus límites |
| `test_phone_cannot_reach_partner_or_admin.py` | La credencial del teléfono recibe 401 en todo `/console/*` de partner y en `/admin/*` |
| `test_phone_list_scope.py` | La lista de teléfonos de la web solo es de quien la pide, y la del admin solo del cliente consultado |

Y además, sin cambios: `test_21_rls_covers_every_tenant_table`,
`test_22_tenant_delete_leaves_nothing` y `test_console_scope`, que ahora también
recorren las rutas nuevas.

## 3. Entrar y quedarse (H1 y H6)

1. Arranca la app en el simulador:

   ```bash
   cd apps/mobile && pnpm ios
   ```

2. En la pantalla de entrada de la app, escribe el correo y la contraseña de la
   persona de cliente (enmienda de R1: nada pasa por la consola).
   - **Esperado:** con una contraseña mala, «El correo o la contraseña no son
     correctos» sin decir cuál; con la buena, dentro, y las pestañas son las de
     `nav`, en ese orden.
   - Con Google configurado en la API: «Continuar con Google» con la cuenta del
     mismo correo entra; con la de otro correo, la app lo dice y deja la
     contraseña.
3. En el admin, quita el módulo Consumo y devuelve la app al primer plano.
   - **Esperado:** la pestaña desaparece sin salir de la sesión (CE-011). Si
     estabas en Consumo, vas a Inicio (R3.5).
4. Entra con una persona de **partner**.
   - **Esperado:** la pantalla «esta app es para los negocios…» y ninguna
     sesión creada (R1.5).
5. En la consola web, abre `/account/phones` y cierra el teléfono.
   - **Esperado:** la siguiente petición de la app la saca a la pantalla de
     entrada (R7.3).
6. «¿Olvidaste tu contraseña?» con el correo de la persona.
   - **Esperado:** el mismo mensaje exista o no la cuenta, y el correo con el
     enlace a la página de la web (R1.7).
6. Haz el mismo cierre desde la pestaña «Acceso» del admin.
   - **Esperado:** el mismo resultado y una fila de auditoría con
     `operator:<correo>`.
7. Fija una versión mínima por encima de la instalada.
   - **Esperado:** la pantalla «actualiza la app» y nada más (R13).
8. Flujo automático:

   ```bash
   maestro test apps/mobile/e2e/sign-in.yaml
   maestro test apps/mobile/e2e/dynamic-tabs.yaml
   ```

## 4. Inicio y Consumo (H5, CE-005)

- **Prueba de API:** `test_lite_phone_figures_match_web` compara Panel y Consumo
  con la credencial del teléfono contra el JWT de la BFF, para el mismo cliente
  y el mismo instante. Deben ser **iguales al céntimo**.
- **A mano:** en Consumo no existe ningún botón ni texto de compra (R4.4).

## 5. Atender (H3 y H4, CE-004)

1. Fuerza un escalado en el cliente de pruebas, abre la conversación y toca
   «Tomar el control».
2. Envía con la red cortada y restablecida. En Maestro:

   ```bash
   maestro test apps/mobile/e2e/send-flaky.yaml
   ```

   Ese flujo hace 100 envíos con cortes forzados.
   - **Esperado:** el contacto recibe cada mensaje **una vez** (CE-004).
   - **Esperado en el registro:** respuestas 201 y 200 de replay, y ningún 500.
3. Con la última entrada del contacto de hace más de 24 h.
   - **Esperado:** el cuadro dice por qué no se puede escribir antes de que la
     persona empiece (R6.5).
4. Toma el control desde la web mientras la app tiene la conversación abierta.
   - **Esperado:** la app enseña quién la atiende ahora (R6.2).

## 6. Avisos (H2 y H7, CE-002, CE-003)

**En un dispositivo físico con build de desarrollo:**

1. Entra por primera vez.
   - **Esperado:** la pantalla propia aparece antes del diálogo del sistema, y
     «Ahora no» no lo lanza (R10).
2. Con la app cerrada, fuerza un escalado.
   - **Esperado:** el aviso llega en menos de 10 s, en el nivel urgente, con el
     nombre del contacto y el motivo (R8.11).
3. Toca el aviso.
   - **Esperado:** abre la conversación. Desde ahí, como mucho 2 toques hasta
     escribir (CE-003).
4. Bloquea el teléfono con el ajuste «Al desbloquear» (iOS) u «ocultar
   contenido sensible» (Android).
   - **Esperado:** el aviso no enseña ni nombre ni texto (R8.10).
5. Apaga el tipo «Esperan a una persona» en Ajustes.
   - **Esperado:** el siguiente escalado no avisa a ese teléfono (R11.2), y la
     entrega queda en `skipped` con `kind_disabled`.
6. Con la conversación abierta en primer plano, escribe como contacto.
   - **Esperado:** no hay banner (R8.7).
7. Revisa en la base:

   ```sql
   select status, skip_reason from client_push_deliveries order by created_at desc limit 10;
   ```

**Payload real.** Con la variable de depuración del worker que registra el
cuerpo enviado, sin el destino, se comprueba a mano lo que el barrido 4 ya
comprueba:
- el título con el nombre y el texto de 100 caracteres como mucho;
- ningún teléfono;
- `url`, `thread-id` o `tag`, y la categoría o el canal del tipo.

## 7. Accesibilidad, tema, idioma y movimiento (R14, CE-008, D24)

- **Pruebas automáticas:**

  ```bash
  cd apps/mobile && pnpm test -- a11y
  ```

  Las consultas por rol y nombre accesible de cada pantalla, con `fontScale`
  máximo y en los dos temas.
- **A mano:** la lista de VoiceOver y TalkBack (las acciones de deslizar tienen
  alternativa sin gesto), con capturas en `evidence/` en claro, oscuro, ES y EN.
- **Movimiento:**
  - con el movimiento reducido activado, «Tomar el control», las entradas de
    mensajes y la recolocación de la Bandeja pasan a fundido o a
    instantáneo;
  - sin él, se graba un vídeo del momento «Tomar el control» para
    `evidence/`;
  - la herramienta de rendimiento del simulador no marca caídas por debajo de
    60 fps.
- **Consola:** la página `/account/phones` pasa axe en el Playwright de la
  consola (proyecto `lite`).

## 8. Piloto

- **Builds:** desde `apps/mobile`, con la API key nueva de App Store Connect.

  ```bash
  eas build -p ios --profile preview
  eas build -p android --profile preview
  ```

- **Distribución:** TestFlight y la prueba interna de Play, para el cliente
  piloto que elija el owner.
- **CE-010:** se mide con los eventos de la conversación (pidió ayuda y control
  tomado) durante dos semanas.
