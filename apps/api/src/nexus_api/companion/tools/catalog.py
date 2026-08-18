"""Las herramientas de lectura, como datos (CO-02, §6.1).

Un catálogo declarativo y no una función por herramienta. Tres motivos, y
los tres se convierten en test:

- **Se puede recorrer.** Comprobar que ninguna acepta ``tenant_id``, que
  todas son ``GET``, que toda ruta existe de verdad en la aplicación y que
  toda descripción es prescriptiva son cuatro bucles sobre esta tabla.
- **Se ve de un vistazo qué puede leer el Companion.** Es la lista blanca
  del §5, capa 2 del aislamiento: el modelo no puede llamar a nada que no
  esté aquí.
- **Añadir una herramienta es añadir una fila.** Sin fila no hay
  herramienta, y con fila hay tests obligatorios.

Sobre las descripciones
-----------------------
Son **prescriptivas** a propósito: dicen *cuándo* llamar, no solo qué
hacen. La guía de migración a Opus 5 mide una mejora real por esto en
modelos recientes, que por defecto tiran poco de herramientas. Cada una
lleva su condición de disparo y su cuándo-no; hay un test que lo exige.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

#: Referencia del cliente. Es el ``external_client_ref`` del partner —su
#: propio nombre para el cliente—, **jamás** un ``tenant_id``. Lo resuelve
#: el router bajo el principal, y un ref de otro partner devuelve el mismo
#: 404 opaco que uno inexistente (garantía C1).
CLIENT_REF = "client_ref"

ParamType = Literal["string", "integer", "boolean"]


@dataclass(frozen=True)
class ToolParam:
    name: str
    type: ParamType
    description: str
    required: bool = False
    enum: tuple[str, ...] | None = None
    minimum: int | None = None
    maximum: int | None = None
    #: Si es ``True`` va en la ruta (``{ref}``); si no, en la query.
    in_path: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """Una herramienta = un endpoint ``/console/*`` de lectura."""

    name: str
    path: str
    description: str
    #: Etiqueta humana. Es lo que el cajón pinta y lo que va en la cita:
    #: "Consultando el consumo de Clínica Boreal", no ``console.get_usage``.
    label: str
    params: tuple[ToolParam, ...] = ()
    #: Recorte de la respuesta antes de entrar al contexto. Sin esto, tres
    #: llamadas a ``get_audit`` llenan la ventana y el resto del turno
    #: responde a ciegas.
    max_chars: int = 8_000
    #: Todas las de CO-02 son ``GET``. El campo existe para que el test que
    #: lo comprueba tenga algo que leer, no por si acaso.
    method: Literal["GET"] = "GET"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_client(self) -> bool:
        return any(p.in_path for p in self.params)

    def json_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self.params:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = list(p.enum)
            if p.minimum is not None:
                prop["minimum"] = p.minimum
            if p.maximum is not None:
                prop["maximum"] = p.maximum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }


def _ref_param(what: str) -> ToolParam:
    return ToolParam(
        name=CLIENT_REF,
        type="string",
        description=(
            f"Referencia del cliente ({what}). Es la que el partner usa para "
            "nombrar a su cliente, la que devuelve console.list_clients. Si el "
            "usuario nombra al cliente de otra forma, resuélvela antes; no la "
            "adivines."
        ),
        required=True,
        in_path=True,
    )


DAYS = ToolParam(
    name="days",
    type="integer",
    description="Ventana en días hacia atrás. Por defecto 30.",
    minimum=1,
    maximum=366,
)


# ── el catálogo ────────────────────────────────────────────────────────

READ_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="console.whoami",
        path="/console/me",
        label="Quién eres en la consola",
        description=(
            "Devuelve quién es la persona con la que hablas: su correo, su rol en "
            "el partner, la lista exacta de permisos que tiene y los datos del "
            "partner. Llama a esto en cuanto el rol importe para responder — antes "
            "de decirle a alguien que puede o no puede hacer algo, antes de "
            "proponerle un camino que quizá su rol no permita, y cuando pregunte "
            "'¿qué puedo hacer yo aquí?'. No lo uses como saludo automático de "
            "cada turno: si la respuesta no depende del rol, es una llamada "
            "desperdiciada."
        ),
        max_chars=2_000,
    ),
    ToolSpec(
        name="console.list_clients",
        path="/console/clients",
        label="Clientes del partner",
        description=(
            "Lista los clientes del partner con su referencia, su nombre, su "
            "estado y su salud (si tiene agente publicado y WhatsApp conectado). "
            "Llama a esto siempre que el usuario nombre a un cliente de forma "
            "aproximada ('el de la clínica', 'la barbería') y necesites su "
            "referencia exacta, y cuando pregunte cuántos clientes tiene o cuáles "
            "están a medio configurar. Si el resultado no deja UNA sola "
            "coincidencia, pregunta cuál — no elijas la más probable. No lo uses "
            "para ver la cuota de clientes: eso es console.get_quota."
        ),
        params=(
            ToolParam(
                name="q",
                type="string",
                description="Búsqueda por nombre o por referencia.",
            ),
            ToolParam(
                name="status",
                type="string",
                description="Filtra por estado del cliente.",
                enum=("active", "suspended", "provisioning"),
            ),
            ToolParam(
                name="limit",
                type="integer",
                description="Máximo de filas. Por defecto 50.",
                minimum=1,
                maximum=200,
            ),
        ),
    ),
    ToolSpec(
        name="console.get_client",
        path="/console/clients/{client_ref}",
        label="Ficha del cliente",
        description=(
            "Devuelve la ficha de un cliente concreto: nombre, estado, zona "
            "horaria, cuándo se creó y su salud. Llama a esto cuando el usuario "
            "pregunte por un cliente en particular y necesites sus datos de "
            "cabecera, o antes de opinar sobre su configuración. No lo uses para "
            "el prompt ni para las herramientas del agente — para eso están "
            "console.get_agent y console.list_tools."
        ),
        params=(_ref_param("el cliente que quieres consultar"),),
        max_chars=3_000,
    ),
    ToolSpec(
        name="console.get_agent",
        path="/console/clients/{client_ref}/agent",
        label="Agente del cliente",
        description=(
            "Devuelve las versiones del agente de un cliente: cuál está publicada, "
            "si hay borrador, el prompt de cada versión, sus herramientas y quién "
            "la promovió. Llama a esto antes de opinar sobre un prompt, antes de "
            "decir qué versión está en producción, y cuando el usuario pregunte "
            "'¿qué le dije yo a este agente?' o 'qué cambió en la última "
            "publicación'. No lo uses para la política de tono y horarios: eso es "
            "console.get_policy."
        ),
        params=(_ref_param("el cliente cuyo agente quieres leer"),),
        max_chars=20_000,
    ),
    ToolSpec(
        name="console.get_policy",
        path="/console/clients/{client_ref}/agent/settings",
        label="Política del agente",
        description=(
            "Devuelve la política del agente de un cliente: identidad y nombre, "
            "tono, idioma, horarios, qué hace al escalar a un humano y si la "
            "revelación de IA está decidida. Llama a esto cuando el usuario "
            "pregunte por el comportamiento del agente fuera del prompt, cuando "
            "haya que revisar la escalada o los horarios, y siempre antes de "
            "hablar de publicar: publicar sin decisión de revelación de IA falla. "
            "No lo uses para el texto del prompt — eso es console.get_agent."
        ),
        params=(_ref_param("el cliente cuya política quieres leer"),),
        max_chars=6_000,
    ),
    ToolSpec(
        name="console.list_tools",
        path="/console/clients/{client_ref}/tools",
        label="Herramientas del agente",
        description=(
            "Devuelve el catálogo real de herramientas disponibles para un cliente "
            "y cuáles tiene activas su agente, más el estado de sus conectores. "
            "Llama a esto cuando el usuario pregunte qué puede hacer el agente de "
            "un cliente, por qué no hace algo que espera, o qué herramienta le "
            "falta. Es también la respuesta correcta a '¿qué integraciones "
            "tenéis?', porque es el catálogo vivo y no un manual que envejece. No "
            "inventes nombres de herramienta que no salgan aquí."
        ),
        params=(_ref_param("el cliente cuyo catálogo quieres leer"),),
        max_chars=12_000,
    ),
    ToolSpec(
        name="console.list_skills",
        path="/console/clients/{client_ref}/skills",
        label="Skills del agente",
        description=(
            "Devuelve las skills de vertical disponibles y cuáles están activas en "
            "el agente de un cliente. Llama a esto cuando el usuario pregunte por "
            "una skill concreta ('¿qué hace la de componentes nativos de "
            "WhatsApp?'), cuando quiera saber qué hay disponible para su vertical, "
            "o cuando el comportamiento del agente sugiera que le falta una. No lo "
            "confundas con las herramientas: las skills son conocimiento y formato "
            "del vertical, no acciones."
        ),
        params=(_ref_param("el cliente cuyas skills quieres leer"),),
        max_chars=10_000,
    ),
    ToolSpec(
        name="console.list_knowledge",
        path="/console/clients/{client_ref}/knowledge",
        label="Conocimiento del cliente",
        description=(
            "Lista los documentos y URLs de conocimiento de un cliente, con su "
            "estado de indexado y cuándo se indexaron por última vez. Llama a esto "
            "cuando el agente responda mal a preguntas de producto o de precios, "
            "cuando el usuario pregunte qué sabe su agente, y cuando sospeches que "
            "un documento quedó a medio indexar. Devuelve metadatos, no el "
            "contenido de los documentos: no cites párrafos de aquí."
        ),
        params=(_ref_param("el cliente cuyo conocimiento quieres listar"),),
        max_chars=8_000,
    ),
    ToolSpec(
        name="console.list_channels",
        path="/console/clients/{client_ref}/channels",
        label="Canales del cliente",
        description=(
            "Lista los canales de un cliente (WhatsApp y los que haya) con su "
            "estado, su número, su proveedor y su rol asignado. Llama a esto "
            "cuando el usuario diga que no le llegan mensajes, cuando pregunte qué "
            "número está conectado, y antes de hablar de enviar nada. Si el "
            "cliente tiene más de un canal activo y ninguno etiquetado, dilo: la "
            "plataforma rechaza el envío en ese caso en vez de adivinar. No lo uses "
            "para averiguar POR QUÉ algo falla — para eso está "
            "console.channel_diagnostics, que trae el veredicto de cada "
            "comprobación."
        ),
        params=(_ref_param("el cliente cuyos canales quieres listar"),),
        max_chars=6_000,
    ),
    ToolSpec(
        name="console.channel_diagnostics",
        path="/console/clients/{client_ref}/channels/diagnostics",
        label="Diagnóstico de canales",
        description=(
            "Devuelve el diagnóstico completo del canal de WhatsApp de un cliente: "
            "cada comprobación con su veredicto y qué hacer si falla — calidad del "
            "número, límite de mensajes, webhook, token, plantillas. Llama a esto "
            "en cuanto el usuario diga 'no funciona', 'no llegan los mensajes' o "
            "'dejó de responder', antes de cualquier hipótesis. Es la herramienta "
            "que convierte una queja en una causa concreta. No la uses para el "
            "gasto ni para el volumen: eso son console.get_usage y "
            "console.conversation_stats."
        ),
        params=(_ref_param("el cliente que quieres diagnosticar"),),
        max_chars=10_000,
    ),
    ToolSpec(
        name="console.list_templates",
        path="/console/clients/{client_ref}/channels/whatsapp/templates",
        label="Plantillas de WhatsApp",
        description=(
            "Lista las plantillas de WhatsApp de un cliente con su estado en Meta "
            "y, cuando hay rechazo, el motivo literal que dio Meta. Llama a esto "
            "cuando el usuario pregunte por qué no puede enviar una campaña, por "
            "qué le rechazaron una plantilla, o qué plantillas tiene aprobadas. "
            "Cita el motivo de Meta tal cual, sin reinterpretarlo. Devuelve 409 si "
            "el cliente no tiene WhatsApp conectado: eso es la respuesta, no un "
            "error que ocultar. No lo uses para las plantillas de arranque de "
            "agente, que son otra cosa (console.get_prompt_library)."
        ),
        params=(_ref_param("el cliente cuyas plantillas quieres listar"),),
        max_chars=10_000,
    ),
    ToolSpec(
        name="console.get_usage",
        path="/console/usage",
        label="Consumo del partner",
        description=(
            "Devuelve el consumo del partner por cliente, canal y periodo, con el "
            "total del mes, el tope y la proyección de fin de mes. Llama a esto "
            "cuando el usuario pregunte por gasto, consumo, factura, proyección o "
            "por qué subió el coste de un cliente. Para ver la evolución día a día "
            "usa después console.usage_series. No lo uses para el coste de Auphere "
            "— eso no se expone."
        ),
        params=(
            ToolParam(
                name=CLIENT_REF,
                type="string",
                description="Limita el consumo a un cliente. Sin esto, todo el partner.",
            ),
            DAYS,
            ToolParam(
                name="source",
                type="string",
                description=(
                    "'channel' es el tráfico real de clientes finales; 'qa' es lo "
                    "que se gastó probando en el playground."
                ),
                enum=("channel", "qa"),
            ),
        ),
        max_chars=10_000,
    ),
    ToolSpec(
        name="console.usage_series",
        path="/console/usage/series",
        label="Serie de consumo",
        description=(
            "Devuelve la serie temporal del consumo, un punto por día. Llama a "
            "esto cuando ya sabes que el gasto subió y hace falta saber CUÁNDO "
            "subió — un salto en un día concreto es lo que convierte 'gastamos "
            "más' en una causa. Úsalo después de console.get_usage, no en su "
            "lugar: la serie sin el total no dice si la cifra es grande o pequeña. "
            "No lo uses para el total del mes ni para la proyección — eso lo "
            "devuelve console.get_usage."
        ),
        params=(
            ToolParam(
                name=CLIENT_REF,
                type="string",
                description="Limita la serie a un cliente.",
            ),
            DAYS,
            ToolParam(
                name="source",
                type="string",
                description="Tráfico real ('channel') o pruebas del playground ('qa').",
                enum=("channel", "qa"),
            ),
            ToolParam(
                name="meter",
                type="string",
                description="Filtra por prefijo de medidor, por ejemplo 'llm.'.",
            ),
        ),
        max_chars=12_000,
    ),
    ToolSpec(
        name="console.conversation_stats",
        path="/console/clients/{client_ref}/conversations/stats",
        label="Estadísticas de conversación",
        description=(
            "Devuelve SOLO metadatos agregados de las conversaciones de un "
            "cliente: cuántas hubo, cuántas se escalaron a un humano, cuántas "
            "tuvieron errores y cómo se reparten en el tiempo. Llama a esto cuando "
            "el usuario pregunte por volumen, por tasa de escalada o por si el "
            "agente está fallando mucho. **No existe ninguna forma de leer lo que "
            "escribió un cliente final, y no la hay a propósito**: si te piden el "
            "texto de una conversación, dilo y ofrece los metadatos."
        ),
        params=(_ref_param("el cliente cuyas estadísticas quieres leer"), DAYS),
        max_chars=6_000,
    ),
    ToolSpec(
        name="console.get_audit",
        path="/console/audit",
        label="Registro de auditoría",
        description=(
            "Devuelve el registro de auditoría del partner: quién hizo qué y "
            "cuándo, con filtros por actor, acción, cliente y fechas. Llama a esto "
            "cuando el usuario pregunte '¿quién publicó esto?', '¿cuándo cambió?' "
            "o 'esto antes funcionaba' — un cambio reciente es la primera "
            "explicación que hay que descartar. Filtra por cliente y por fecha en "
            "vez de traerte el registro entero. No lo uses para saber el estado "
            "ACTUAL de nada: el registro dice qué pasó, no cómo está ahora."
        ),
        params=(
            ToolParam(
                name=CLIENT_REF,
                type="string",
                description="Limita el registro a un cliente.",
            ),
            ToolParam(
                name="action",
                type="string",
                description="Filtra por prefijo de acción, por ejemplo 'agent.'.",
            ),
            ToolParam(
                name="actor",
                type="string",
                description="Filtra por actor (coincidencia parcial del correo).",
            ),
            ToolParam(
                name="limit",
                type="integer",
                description="Máximo de entradas. Por defecto 50.",
                minimum=1,
                maximum=200,
            ),
        ),
        max_chars=12_000,
    ),
    ToolSpec(
        name="console.get_onboarding",
        path="/console/onboarding",
        label="Puesta en marcha del partner",
        description=(
            "Devuelve qué le falta al partner para estar operativo: los pasos de "
            "alta pendientes y los completados. Llama a esto cuando el usuario sea "
            "nuevo, cuando pregunte 'por dónde empiezo' o '¿qué me falta?', y "
            "cuando algo no funcione y sospeches que el partner nunca terminó de "
            "configurarse. Es del PARTNER: no lo uses para saber qué le falta a un "
            "cliente concreto, que es console.get_client y su salud."
        ),
        max_chars=4_000,
    ),
    ToolSpec(
        name="console.get_quota",
        path="/console/home",
        label="Resumen y cuota del partner",
        description=(
            "Devuelve el resumen del partner: clientes usados contra el máximo "
            "contratado, conversaciones del periodo, unidades de consumo, agentes "
            "con incidencias y acciones pendientes. Llama a esto ANTES de plantear "
            "dar de alta un cliente nuevo — si no queda cuota, el alta falla y más "
            "vale decirlo antes— y cuando el usuario pida una foto general de cómo "
            "va todo. No lo uses para el desglose del gasto: eso es "
            "console.get_usage."
        ),
        max_chars=4_000,
    ),
    ToolSpec(
        name="console.get_prompt_library",
        path="/console/seed-templates",
        label="Biblioteca de plantillas de agente",
        description=(
            "Devuelve las plantillas de arranque de agente disponibles por "
            "vertical, con qué datos pide cada una. Llama a esto cuando el usuario "
            "quiera crear un agente y haya que elegir punto de partida, o cuando "
            "pregunte qué verticales hay cubiertos. Es la materia prima de una "
            "alta: proponer un prompt desde cero cuando existe una plantilla del "
            "vertical es trabajo peor hecho. No confundas estas plantillas con las "
            "de WhatsApp, que son console.list_templates."
        ),
        max_chars=12_000,
    ),
)

TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in READ_TOOLS}


def tool_specs() -> list[dict[str, Any]]:
    """El catálogo en el formato de herramientas del proveedor."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.json_schema(),
            },
        }
        for t in READ_TOOLS
    ]


__all__ = [
    "CLIENT_REF",
    "READ_TOOLS",
    "TOOLS_BY_NAME",
    "ToolParam",
    "ToolSpec",
    "tool_specs",
]
