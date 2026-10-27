# Quickstart — spec 047

Cómo ver y comprobar lo que construye esta spec, ola por ola. Lo que no se pueda
hacer en la máquina queda escrito en `evidence/hallazgos.md`, con su razón.

## 1. Arrancar

```bash
docker compose up -d
```

```bash
curl -s http://localhost:8000/health
```

Además de la API, hacen falta:
- **el worker**: el constructor, las lecturas, las pruebas, los crons de bolsas y
  del cambio, y las sugerencias corren en él;
- **la consola** (`apps/console`) y **el panel de operador** (`apps/admin`), con
  sus servidores de desarrollo;
- **la app** (`apps/mobile`), con el cliente de desarrollo de la 042 contra la API
  local (`EXPO_PUBLIC_API_URL`).

La semilla de esta spec (tarea de la fase 1) crea:
- un partner «Ladrian Studio» con la consola nueva activada y la cuenta en EUR;
- un partner «Demo USD» sin activar, para ver la consola de hoy;
- los clientes del prototipo: Flor y Encanto (USD), Clínica Dental Sonrisa,
  ADSL System y Café Origen. Café Origen no tiene agentes;
- personas de cada rol (owner, admin, builder, analyst y billing) y una persona
  del cliente para la consola lite y la app.

```bash
cd apps/api && uv run python scripts/dev_seed_fabrica.py [--password '...']
```

**Sin credenciales de Meta**, la consola dice «El número lo conecta Auphere»
(requisito 30.10). Los canales de la semilla se crean ya conectados.

**Modelos en local**:
- la API y el worker usan los proveedores que haya en `apps/api/.env.local`;
- los despliegues de Bedrock solo se prueban en staging, con el rol de la tarea;
- un perfil de catálogo de desarrollo apunta todas las tareas a un modelo barato
  certificado con la batería mínima. Así se ve el router decidir sin coste real.

## 2. Recorridos por ola

### Ola 1 — Ningún mensaje se pierde y el turno es fiable

1. Vaciar la bolsa de Flor y Encanto y enviar un mensaje al canal de prueba
   (simulador de webhook). Debe aparecer en la Bandeja como «Espera a una
   persona · Sin saldo», con el aviso al partner y a Marta.
2. Enviar «hola», «quería una cita» y «para mañana» en menos de 3 s. Un solo turno
   y una sola respuesta.
3. Forzar un reintento del turno (matar el worker a mitad) y comprobar que la
   reserva y la respuesta no se duplican.

### Ola 2 — Clientes y ficha

1. «Nuevo cliente»: nombre, nicho y una información con web, `@usuario` y un correo.
   Los chips no toman el correo por web.
2. Crear: lleva al Panel, con la tarjeta de lectura. Al terminar, los datos leídos
   salen «Leído de la web · revísalo», y lo que contradice un dato escrito queda
   como sugerencia.
3. Negocio › Horarios: un turno 22:00–03:00 («Nocturno · cierra al día
   siguiente»), una fecha especial cerrada y otra con horario propio. Ver la frase
   «Así lo dirá el agente».
4. Servicios: uno no reservable sin duración, uno gratis y uno con precio en CLP.
   Marcar uno «Solo Ventas mayoristas».
5. Desde la app, como Marta: cambiar el horario del sábado. El siguiente mensaje
   del simulador dice el horario nuevo, y el partner ve el aviso y la procedencia
   «Escrito por Marta desde la app».

### Ola 3 — Constructor, playground, pruebas y puerta

1. Café Origen › «Nuevo agente»: nombre y «¿Qué tiene que hacer?». «Generar
   borrador» escribe por bloques en menos de 30 s, hace como mucho 5 preguntas y
   dice cuántas descartó.
2. Playground: hora simulada mañana a las 23:30, una reserva que el agente «habría
   hecho» y la agenda simulada que cambia.
3. Pruebas: 8 del caso y 12 del sector, 3 pasadas. Provocar una inestable y una
   crítica en rojo.
4. «Guardar»: la puerta bloquea con la crítica en rojo. Como builder no aparece
   «Guardar igualmente»; como owner, sí, pidiendo el motivo.
5. Arreglar, guardar, «Deshacer» antes de 10 minutos y «Restaurar» desde el historial.

### Ola 4 — Agentes y canales

1. Pausar y reanudar un agente desde la consola y desde la app. Comprobar el motivo
   y el autor.
2. Conectar WhatsApp desde el agente: se abre el asistente de la spec 046 con el
   agente ya elegido. Pregunta si el número ya se usa en la app WhatsApp Business
   (sí: coexistencia, que es lo recomendado; no: Cloud API). El catálogo enseña lo
   que viene como «Próximamente», sin poder iniciarse. Sin credenciales de Meta,
   dice «El número lo conecta Auphere». Un número recién conectado queda en modo
   prueba («Solo mi equipo»).
3. Enlace del dueño: crearlo, copiarlo, intentar crear otro (ofrece revocar el
   pendiente) y revocarlo.
4. Página del canal: «Solo mi equipo» exige un número de prueba; «A todos» con una
   excepción; tres destinatarios de escalado; deshacer el cambio.
5. Eco de coexistencia (simulador): un mensaje del negocio desde la app pone la
   conversación en «La lleva una persona» 2 horas, y el agente no responde.

### Ola 5 — Integraciones y conocimiento

1. Autorizar Google Calendar una vez y activarlo en dos agentes con permisos
   distintos. Comprobar que un tercer agente no ve sus herramientas.
2. «Enseñar» un dato con «Solo este agente» y comprobar que el agente hermano no lo
   sabe (prueba adversarial de la garantía 9).

### Ola 6 — Modelos y router

1. Un agente en «Automático»: preguntar el horario y comprobar el `llm.route_decision`
   (tarea `answer`, perfil, descartes, elegido y coste).
2. Provocar un argumento inválido de una herramienta: escala con subllamada y el
   registro lo dice.
3. Marcar el despliegue elegido «No disponible» en el admin: el turno siguiente usa
   la alternativa.
4. Un cliente con «Solo UE» y sin alternativa en la UE: la conversación va a la
   Bandeja con «Sin modelo disponible».
5. Calidad del agente: pasar a «Máximo», ver el precio estimado y «Comprobando la
   calidad…», guardar y deshacer.

### Ola 7 — Dinero

1. Asignar 20 USD a Flor y Encanto desde una cuenta en EUR: el recibo con el cambio
   del BCE y lo que queda en la cuenta.
2. Bajar la bolsa, mover saldo a otro cliente y programar «Rellenar cada mes hasta
   50». Simular el día 1 con la cuenta corta.
3. Tope de 15 USD en Ventas mayoristas: al 80 % avisa y al 100 % pasa a la Bandeja
   con «Tope del agente», y el resto sigue.
4. Como builder, «Pedir saldo» y repetirlo: la segunda vez dice «Pedido hace…».
5. Consumo: las cuatro partidas, la gráfica de 7, 30 y 90 días, y el CSV.

### Ola 8 — Consola, consola lite y app

1. ⌘K «Recep»: aparecen los agentes con su cliente. Flechas, Intro y Escape.
2. A 390 px: sin desbordamiento horizontal en todas las pantallas. Con «Reducir
   transparencia», el vidrio pasa a sólido.
3. App: Agentes y Negocio, sin conexión (no guarda y lo dice), y los avisos push
   nuevos con su pantalla.

### Ola 9 — Mejora y Recepción

1. Con conversaciones sembradas (12 sobre el aparcamiento), generar las sugerencias
   de la semana. Ninguna respuesta de la API lleva cuerpos de mensaje.
2. Desde la Bandeja de la app: «Corregir esta respuesta» con un dato (se aplica) y
   con un comportamiento (llega al partner con la paráfrasis).
3. Recepción con dos destinos: «quiero comprar al por mayor» deriva, y la tercera
   ida y vuelta pasa a una persona.

### Ola 10 — Migración y activación

1. Con una copia anonimizada de producción en staging, correr la migración en modo
   ensayo para Facelad y Amacrux, y leer el informe: la batería y la audiencia por
   número, antes y después.
2. Activar un partner, repartir el saldo en bolsas y desactivar antes de confirmar:
   vuelve la consola de hoy con los datos de antes.

## 3. Estados en cada pantalla

Ideal, vacío, cargando (esqueleto), error con «Reintentar», parcial y sin permiso
(la acción no aparece), en claro y en oscuro. En las vistas en vivo (el progreso
del constructor, el playground y la Bandeja), además, «reconectando». Comprobar también con texto largo
(alemán) y al 200 % de zoom.

## 4. Verificar

```bash
./scripts/verify.sh
```

```bash
cd apps/api && uv run pytest tests/isolation/ -x
```

La segunda línea es la suite de aislamiento. Su rojo bloquea la fusión, y las
suites de pytest se corren de una en una (memoria del repo).

## 5. Lo que no se prueba en local

- **Embedded Signup v5 real y la coexistencia con un número de verdad**: en staging,
  con un número de pruebas de Auphere, nunca de un cliente.
- **El enlace del dueño en iOS y Android**: en staging. Hasta que esté probado, la
  consola no lo presenta como «desde su teléfono» (requisito 31.3).
- **Bedrock y Scaleway**: en staging, con las cuotas comprobadas y los
  subprocesadores dados de alta.
- **Push real y builds de la app**: no se lanzan sin que Luis lo pida (`docs/app-movil.md`).
