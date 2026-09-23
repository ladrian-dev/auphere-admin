# Contratos de pantalla (consola) — spec 017

Qué ve y qué puede hacer cada rol. Sin detalle de componentes; eso va en `tasks.md`.
Cada pantalla tiene su tabla de paridad en `parity.md` antes de implementarse.

## Ficha del cliente (`/clients/{ref}`, cabecera común) — iteración 1

| Condición | Lo que se ve |
|---|---|
| Cualquier rol con `clients:read` | Nombre · estado · teléfono conectado (si hay) · **Puesta en marcha**: cuatro puntos con nombre (agente · canal · cupo · activo) · **Cupo**: barra «3 800 de 5 000 créditos» o «Sin tope: consume del saldo del partner» |
| Falta algo y el rol puede resolverlo | Un botón con la acción del primer paso pendiente: «Preparar el agente» → Agente · «Conectar un canal» → Canales · «Asignar cupo» → diálogo de tope · «Activar» → confirmación |
| Falta algo y el rol no puede | El paso pendiente se ve; sin botón (§V) |
| Atendiendo | Una línea «Atendiendo desde el {fecha}»; sin botón |
| `clients:write` | Menú «Más»: Pausar / Reactivar / Archivar; **Eliminar solo si archivado** (`clients:delete`) |
| Navegación | Tres grupos con nombre: Configurar (Agente, Ajustes, Capacidades, Conocimiento) · Conectar (Canales, Integraciones, Puesto de trabajo) · Observar (Resumen, Conversaciones, Playground), filtrados por permiso de lectura; grupo vacío no se pinta; < 768 px: selector con `optgroup` |
| Hay borrador | **Barra de borrador** pegada bajo la navegación (abajo en móvil): «Cambios sin publicar en Ajustes y Capacidades · Ver diferencias · Publicar»; sin `agents:write`: la misma frase y «Puede publicar: propietario, administrador o builder» |
| «Ver diferencias» | Hoja con secciones por pantalla; el prompt completo plegado al final |
| «Publicar» | Misma confirmación que Agente; al confirmar, la barra desaparece y Agente muestra la versión nueva activa |

Rutas: `/clients/{ref}/tools` y `/clients/{ref}/skills` **redirigen** a
`/clients/{ref}/capabilities`; `/clients/{ref}/tools#integraciones` a
`/clients/{ref}/integrations`. Ningún enlace antiguo se rompe (R12.5).

## Capacidades (`/clients/{ref}/capabilities`) e Integraciones (`/clients/{ref}/integrations`) — iteración 2

| Condición | Lo que se ve |
|---|---|
| Integraciones | Una tarjeta por conector: logo, qué es, qué desbloquea (funciones), estado, acción (Conectar / Enlazar / Reconectar / Desconectar / Sincronizar) con las reglas de la 016 |
| Capacidades, cliente con sector | Grupos por función; solo sector + comunes; línea «{n} capacidades de otros sectores · Ver todas»; «Recomendadas para tu sector» como etiqueta en la tarjeta |
| Capacidades, sin sector | Todo el catálogo agrupado; línea «Este cliente no tiene sector; se muestran todas» |
| Tarjeta | Nombre de negocio · descripción · etiqueta de función · conmutador (`agents:write`) o estado (solo lectura) · «En la versión activa» si aplica · modo (Siempre / Nunca) solo para herramientas · «Necesita {integración} · Conectar» cuando falta · detalle plegado «Técnico: nombre, tipo, versión, etiquetas» |
| Buscador | Filtra en la vista actual por nombre y descripción; «Ver todas» amplía |
| Acciones de lote | «Marcar todas las visibles» / «Desmarcar todas» (paridad con Herramientas), cada una una llamada por capacidad con progreso visible |
| Un clic | Guarda en el borrador; aparece la barra de borrador; toast solo confirma |

## Consumo (`/usage`) — iteración 3

| Bloque | Lo que se ve |
|---|---|
| **Saldo** | «25 000 créditos» (incluido + comprado) · «≈ 250 USD · ≈ 4 100 mensajes (estimación)» · caducidad del incluido · botón «Comprar crédito» (`billing:manage`) · panel plegable «Alertas» con umbral y destinatarios (`usage:manage`) · si no se pudo leer: «No pudimos leer tu saldo · Reintentar», el resto sigue |
| **Reparto por cliente** | Fila por cliente: nombre · barra «restante de tope» · «Sin cupo» si aplica · botón «Ajustar» → diálogo con dos pestañas: Editar tope / Mover a otro cliente (una operación) · «Asignar cupo» para clientes sin asignación (`usage:write`) |
| **Consumo** | Filtros (cliente, tipo, periodo) · gráficas · tabla con Mensajes / Modelo / Multimedia / Voz y fuente Canal / Pruebas · exportar CSV (paridad) |

## Nuevo cliente (`/clients/new`) — iteración 4

| Paso | Lo que se ve |
|---|---|
| 1 Datos | Nombre · Zona horaria (propuesta, selector con nombres) · «Avanzado» plegado: Referencia (misma validación) |
| 2 Sector | Tarjetas por sector con icono y una frase; ninguna elegida; al elegir: datos obligatorios primero, opcionales plegados |
| 3 Revisión | Resumen · «Publicar y activar» (marcado si hay plantilla) · etapas visibles y reintentables (016) |
| Fin | Ficha del cliente con la cabecera señalando «Conectar un canal» |

## Inicio (`/`) y Clientes (`/clients`) — iteración 5

| Pantalla | Lo que se ve |
|---|---|
| Inicio | Tarjeta «Ponte en marcha» (pasos pendientes con acción; canal = cliente final, conversación = de canal) · dentro, «Tu puesto de trabajo» solo con plan con teammates · métricas con etiqueta en sans, sin «calculado en» · incidencias como hoy |
| Clientes | Columnas: Nombre · Puesta en marcha (3 puntos con nombre) · Cupo restante (barra) · Conversaciones 7 d · Actualizado · fila entera clicable, nombre como enlace · filtros de estado con contador · búsqueda por nombre y referencia |

## Ajustes del agente (`…/agent/settings`) — iteración 6

Secciones plegables (Identidad, Tono, Horario, Idiomas, Escalado, Aviso de IA,
Modelo) con resumen de una línea; índice lateral (superior < 1024 px); pie fijo
con Guardar y estado; selectores de zona horaria e idiomas con nombres y
búsqueda; contador de caracteres; Horario con «Atiende siempre» explícito.

## Transversal — iteración 7

`HelpHint` en cada término (cupo, créditos, capacidad, integración, sector,
borrador, versión, escalado, puesta en marcha); `/ayuda` con el glosario;
Playground (hilo con fecha, presupuesto en una línea, error con causa);
Ajustes del cliente (Datos con referencia copiable · Zona de peligro);
Facturación (correo editable); Notificaciones y Auditoría (títulos de negocio,
filtro por categoría). Ningún rótulo en monoespaciado fuera de identificadores.
