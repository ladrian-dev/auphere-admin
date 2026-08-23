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

from nexus_api.core.respond_catalog import RESPOND_MODEL_IDS

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


#: Clase de la herramienta (§23.1 de la investigación, §6 del contrato).
#:
#: - ``read``     — consulta el estado. No cambia nada.
#: - ``propose``  — calcula un cambio y devuelve previsualización, diff e
#:                  impacto. **Tampoco cambia nada**: solo lee.
#: - ``mutates``  — escribe. Hay exactamente una en todo el catálogo.
#: - ``trial``    — prueba el agente BORRADOR en el playground (CO-05). No
#:                  toca la configuración del cliente, no llega a ningún
#:                  cliente final y no cambia qué está publicado: por eso no
#:                  pasa por ``propose → confirm → apply``. Exigir una
#:                  confirmación para *probar* convierte la prueba en
#:                  fricción, y la fricción es justo lo que hace que la gente
#:                  publique sin probar.
ToolClass = Literal["read", "propose", "mutates", "trial"]

#: Política de permiso, copiada de Managed Agents. Es un **dato por
#: herramienta que lee el motor**, no una instrucción de prompt: el modelo no
#: decide nada de esto y no puede convencerse a sí mismo de lo contrario.
PermissionPolicy = Literal["always_allow", "always_ask"]


@dataclass(frozen=True)
class ToolSpec:
    """Una herramienta = un endpoint ``/console/*``."""

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
    #: El método con el que la herramienta **lee**. Sigue siendo ``GET`` en
    #: todas: las ``propose`` leen para calcular el diff, y la única que
    #: escribe (``console.apply``) no sale por aquí — su petición la arma el
    #: mapa de aplicación por ``kind``, desde el payload ya confirmado.
    method: Literal["GET", "POST"] = "GET"
    tool_class: ToolClass = "read"
    permission_policy: PermissionPolicy = "always_allow"
    #: Solo para ``propose``: el ``kind`` de acción que produce (§3.1 del
    #: contrato). Es lo que ata la herramienta con el endpoint de aplicación.
    kind: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Las invariantes del §6 del contrato, comprobadas al CONSTRUIR.

        Un ``mutates`` con ``always_allow`` no es que rompa un test: no se
        puede llegar a existir. Es la diferencia entre una regla y una
        convención — y la razón de que la garantía C4 se pueda afirmar sobre
        el catálogo entero en vez de sobre las filas que alguien recordó
        revisar.
        """
        if self.tool_class == "mutates" and self.permission_policy != "always_ask":
            raise ValueError(
                f"{self.name}: una herramienta 'mutates' exige 'always_ask'. "
                "Escribir sin registro de confirmación es exactamente lo que "
                "la garantía C4 prohíbe."
            )
        if self.tool_class == "read" and self.permission_policy != "always_allow":
            raise ValueError(f"{self.name}: una lectura no pide permiso; es 'always_allow'.")
        if (self.tool_class == "propose") != (self.kind is not None):
            raise ValueError(f"{self.name}: 'kind' es exactamente de las herramientas 'propose'.")
        if self.tool_class == "trial" and self.permission_policy != "always_allow":
            raise ValueError(
                f"{self.name}: probar no pide permiso. Una prueba que exige "
                "confirmación es una prueba que nadie hace."
            )
        if self.method != "GET" and self.tool_class != "trial":
            raise ValueError(
                f"{self.name}: solo una herramienta 'trial' puede no ser GET, y "
                "aun así no escribe nada del cliente."
            )

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
        name="console.list_playbook",
        path="/console/knowledge",
        label="Playbook del partner",
        description=(
            "Lista los documentos del playbook del partner (metadatos: título, "
            "estado, fecha). Llama a esto cuando pregunten por el playbook, las "
            "reglas comunes a todos los clientes, o qué sabe la consola a nivel "
            "de partner. Devuelve metadatos, no el contenido: no cites párrafos "
            "de aquí. No lo confundas con console.list_knowledge, que es el KB "
            "de UN cliente."
        ),
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
        name="console.get_wallet",
        path="/console/wallet",
        label="Cuota del partner",
        description=(
            "Devuelve el libro de cuota del partner: tokens incluidos restantes, "
            "tokens comprados restantes, disponible, reserva (disponible menos la "
            "suma de topes) y si el libro está agotado. Llama a esto cuando el "
            "usuario pregunte por tokens, cupo, reserva, recarga o si queda "
            "saldo para asignar a un cliente. Las cifras son tokens de cuota, "
            "nunca euros. No lo uses para el consumo del mes ni para la "
            "proyección: eso es console.get_usage. Tampoco para el tope de un "
            "cliente: eso es console.list_allocations."
        ),
        max_chars=3_000,
    ),
    ToolSpec(
        name="console.list_allocations",
        path="/console/wallet/allocations",
        label="Asignaciones de cuota",
        description=(
            "Lista las asignaciones de cuota del partner: cada fila es un "
            "client_ref con su tope y lo que le queda. Nunca trae tenant_id. "
            "Llama a esto cuando el usuario pregunte cuánto cupo tiene un "
            "cliente, a quién se le asignó, o antes de proponer un cambio de "
            "tope. Si un cliente no aparece, aún no tiene fila de asignación. "
            "No lo uses para el saldo del partner entero: eso es "
            "console.get_wallet. No inventes un tenant_id."
        ),
        max_chars=8_000,
    ),
    ToolSpec(
        name="console.list_models",
        path="/console/models",
        label="Catálogo de modelos",
        description=(
            "Lista los tres modelos con los que un cliente puede responder: "
            "openai/gpt-5.6-sol (Sol), openai/gpt-5.6-terra (Terra) y "
            "openai/gpt-5.6-luna (Luna). Llama a esto cuando el usuario "
            "pregunte qué modelos hay, cuál usar, o antes de proponer un "
            "cambio de modelo. Es un catálogo cerrado: no hay alias "
            "gpt-5.6 y no aparecen classify, Companion ni whisper. No lo "
            "uses para el modelo actual de un cliente — eso es "
            "console.get_client_model — ni para el cupo."
        ),
        max_chars=2_000,
    ),
    ToolSpec(
        name="console.get_client_model",
        path="/console/clients/{client_ref}/model",
        label="Modelo del cliente",
        description=(
            "Devuelve el modelo de respuesta (rol respond) de un cliente: "
            "el model_id, el nombre y si hay fila de binding. Llama a esto "
            "cuando el usuario pregunte en qué modelo corre un cliente, "
            "antes de proponer un cambio, y para enseñar el antes y el "
            "después. Si no hay fila, before queda vacío: el cliente aún "
            "no tiene binding. Un ref de otro partner es el mismo 404 "
            "opaco que uno inexistente. No lo uses para listar el catálogo "
            "— eso es console.list_models — ni para classify o whisper."
        ),
        params=(_ref_param("el cliente cuyo modelo quieres leer"),),
        max_chars=2_000,
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
    # CO-08, §5 de CONTRACT-V2. Es R1 aplicada a las capacidades: **si algo
    # no está en el catálogo leído en este turno, no existe**. Vive aquí y
    # no en el prompt de sistema a propósito — un límite horneado en el
    # prompt no deja cita, no deja ``tool.call.started`` y no se puede
    # versionar sin invalidar el caché del prompt estable. Leerlo deja las
    # tres cosas, y por eso el Companion puede decir "esto no está" con la
    # misma procedencia con la que dice "tu agente va por la v7".
    ToolSpec(
        name="console.get_workflow",
        path="/console/clients/{client_ref}/workflow",
        label="Pack del cliente",
        description=(
            "Devuelve el pack v1 de un cliente: trigger, steps cerrados "
            "(send_template, wait_reply, end), plantilla, cron (hora en zona "
            "del partner) y si está activo. Llama a esto antes de proponer "
            "un pack y cuando pregunten qué automatización tiene un cliente. "
            "Un ref ajeno es el mismo 404 opaco que uno inexistente. No lo "
            "uses para el agente ni para el playground. No hay chip Workflow "
            "en el chat del cliente final."
        ),
        params=(_ref_param("el cliente cuyo pack quieres leer"),),
        max_chars=4_000,
    ),
    ToolSpec(
        name="console.list_workflow_runs",
        path="/console/clients/{client_ref}/workflow/runs",
        label="Runs del pack",
        description=(
            "Lista los runs del pack de un cliente: thread_id y status. "
            "interrupted no es un error: el pack está esperando respuesta. "
            "Llama a esto cuando pregunten si corrió el pack o cómo va. "
            "No lo uses para leer el pack — eso es console.get_workflow. "
            "No expongas LangSmith ni LiteLLM. Un ref ajeno es 404 opaco."
        ),
        params=(_ref_param("el cliente cuyos runs quieres listar"),),
        max_chars=6_000,
    ),
    ToolSpec(
        name="console.get_capabilities",
        path="/console/capabilities",
        label="Qué existe y qué no en Auphere",
        description=(
            "Devuelve el documento versionado de capacidades y límites de la "
            "plataforma: qué conectores y canales hay, qué está planificado, qué "
            "no existe, qué está fuera de alcance y por qué, y qué se retiró y a "
            "favor de qué. Llama a esto ANTES de decir que algo no se puede, "
            "antes de prometer que algo llega, y antes de ofrecer un ticket de "
            "soporte — sin haberlo leído no sabes si estás mandando a la persona "
            "contra un muro que no existe. Lo que no esté aquí no existe: no lo "
            "deduzcas del nombre de una herramienta ni de lo que sabías de antes."
        ),
        max_chars=16_000,
    ),
)

# ── propuesta (CO-04, §6.2) ────────────────────────────────────────────
#
# Nueve herramientas que **calculan** un cambio y devuelven previsualización,
# diff e impacto. Ninguna escribe: leen por ``/console/*`` igual que las de
# arriba y hacen el resto en Python. Lo que producen se guarda en
# ``companion.actions`` y no se aplica hasta que una persona lo confirma.
#
# ``path`` es el endpoint que la propuesta LEE para calcular el diff, no el
# que la aplicaría — ese vive en ``APPLY_ROUTES`` de ``proposals.py`` y está
# atado por el ``kind``. Separarlos es lo que permite que la propuesta corra
# con permisos de lectura y solo la aplicación pida los de escritura.


def _propose_ref(what: str) -> ToolParam:
    """La referencia del cliente, en la ruta de LECTURA de la propuesta."""
    return ToolParam(
        name=CLIENT_REF,
        type="string",
        description=(
            f"Referencia del cliente ({what}). La que devuelve "
            "console.list_clients. Si el usuario lo nombra de otra forma, "
            "resuélvela antes; no la adivines."
        ),
        required=True,
        in_path=True,
    )


PROPOSE_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="console.propose_client",
        kind="client",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/me",
        label="Proponer un cliente nuevo",
        description=(
            "Prepara el alta de un cliente nuevo y comprueba la cuota ANTES de "
            "proponer nada. Devuelve la ficha completa a crear y cuánta cuota "
            "queda; no crea nada. Llama a esto cuando el usuario quiera dar de "
            "alta un cliente y tengas ya el nombre, el vertical, la zona "
            "horaria y qué NO debe hacer el agente — si te falta alguno de "
            "esos cuatro, pregúntalo primero, no lo inventes. El alta es "
            "IRREVERSIBLE: no hay forma de deshacerla desde aquí."
        ),
        params=(
            ToolParam(
                name="client_ref",
                type="string",
                description=(
                    "La referencia que el partner usará para este cliente. "
                    "Letras, números, punto, guion, guion bajo y dos puntos."
                ),
                required=True,
            ),
            ToolParam(
                name="name",
                type="string",
                description="Nombre comercial del cliente, tal y como lo dice el usuario.",
                required=True,
            ),
            ToolParam(
                name="timezone",
                type="string",
                description="Zona horaria IANA del cliente (ej. America/Caracas). Por defecto UTC.",
            ),
            ToolParam(
                name="language",
                type="string",
                description="Idioma principal de atención, código ISO corto (es, en, pt).",
            ),
            ToolParam(
                name="vertical",
                type="string",
                description=(
                    "A qué se dedica el cliente. Si encaja con una plantilla "
                    "de console.get_prompt_library, usa su referencia exacta; "
                    "si no, describe el sector en dos palabras."
                ),
            ),
            ToolParam(
                name="forbidden_behaviour",
                type="string",
                description=(
                    "Qué NO debe hacer el agente de este cliente, con sus "
                    "palabras. Pregúntalo: es el dato que nadie da por su "
                    "cuenta y el que causa los incidentes. No lo inventes ni "
                    "lo rellenes con un valor genérico."
                ),
            ),
            # Cada plantilla de vertical pide LO SUYO además de los cinco
            # campos fijos: la de clínica estética quiere la dirección. No se
            # pueden declarar todos aquí —dependen de la plantilla elegida—,
            # así que entran por una sola puerta y el motor comprueba cuáles
            # faltan leyendo la plantilla. Sin esto, el alta se confirma y
            # falla después con un 422, que es el peor momento posible para
            # descubrirlo: la persona ya dijo que sí a algo irreversible.
            ToolParam(
                name="template_fields",
                type="string",
                description=(
                    "Los datos extra que pida la plantilla del vertical, uno "
                    "por línea con la forma clave=valor (por ejemplo "
                    "address=Av. Principal 123, Caracas). Déjalo vacío la "
                    "primera vez: si la plantilla necesita algo, te lo diré y "
                    "se lo preguntas a la persona. No inventes ninguno."
                ),
            ),
        ),
    ),
    ToolSpec(
        name="console.propose_prompt",
        kind="prompt",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/clients/{client_ref}/agent",
        label="Proponer un cambio de prompt",
        description=(
            "Calcula el diff línea a línea entre el prompt actual del agente y "
            "el que propones, y lo deja pendiente de confirmación. Escribe el "
            "prompt COMPLETO, no un fragmento ni un parche: lo que mandes "
            "sustituye al anterior entero. Llama a esto cuando el usuario "
            "describa un comportamiento que falla y tengas un ejemplo real; si "
            "no lo tienes, pídelo — un prompt cambiado a ciegas rompe lo que "
            "funcionaba. Esto crea un BORRADOR: no publica nada."
        ),
        params=(
            _propose_ref("cuyo prompt vas a cambiar"),
            ToolParam(
                name="system_prompt",
                type="string",
                description="El prompt completo que sustituye al actual.",
                required=True,
            ),
        ),
        max_chars=12_000,
    ),
    ToolSpec(
        name="console.propose_policy",
        kind="policy",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/clients/{client_ref}/agent/settings",
        label="Proponer un cambio de política",
        description=(
            "Cambia campos concretos de la política del agente (objetivo, "
            "idioma, zona horaria, mensaje de cierre, escalado a humano) sobre "
            "el borrador. Solo se tocan los campos que pases; el resto queda "
            "como está. Llama a esto cuando el cambio sea de configuración y "
            "no de redacción — si lo que hay que cambiar es CÓMO habla el "
            "agente, eso es console.propose_prompt. La revelación de IA no se "
            "toca desde aquí y no se puede desactivar."
        ),
        params=(
            _propose_ref("cuya política vas a cambiar"),
            ToolParam(
                name="objective",
                type="string",
                description="Para qué existe el agente, en una o dos frases.",
            ),
            ToolParam(
                name="primary_language",
                type="string",
                description="Idioma principal de atención (es, en, pt…).",
            ),
            ToolParam(
                name="timezone",
                type="string",
                description="Zona horaria IANA del horario de atención.",
            ),
            ToolParam(
                name="closed_message",
                type="string",
                description="Qué responde el agente fuera del horario de atención.",
            ),
            ToolParam(
                name="escalation_enabled",
                type="boolean",
                description="Si el agente puede pasar la conversación a una persona.",
            ),
            ToolParam(
                name="handoff_message",
                type="string",
                description="Qué dice el agente justo antes de pasar a una persona.",
            ),
        ),
    ),
    ToolSpec(
        name="console.propose_tools",
        kind="tools",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/clients/{client_ref}/tools",
        label="Proponer un cambio de herramientas",
        description=(
            "Activa o desactiva herramientas del agente sobre el borrador. "
            "Pasa la lista COMPLETA de las que deben quedar activas, separadas "
            "por comas: lo que no esté en la lista se desactiva. Llama a "
            "console.list_tools antes para saber qué hay y cuáles están ya "
            "activas — proponer una lista sin haberla leído desactiva cosas "
            "que nadie pidió desactivar. Una herramienta con conector necesita "
            "que el conector esté conectado; si no lo está, dilo."
        ),
        params=(
            _propose_ref("cuyas herramientas vas a cambiar"),
            ToolParam(
                name="tools",
                type="string",
                description=(
                    "Nombres de herramienta separados por comas, la lista "
                    "completa que debe quedar activa. Cadena vacía = ninguna."
                ),
                required=True,
            ),
        ),
    ),
    ToolSpec(
        name="console.propose_skills",
        kind="skills",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/clients/{client_ref}/skills",
        label="Proponer un cambio de skills",
        description=(
            "Igual que console.propose_tools pero para las skills de vertical: "
            "pasa la lista completa que debe quedar activa. Lee "
            "console.list_skills antes. Una skill que no sea activable no se "
            "puede encender y la propuesta la rechazará."
        ),
        params=(
            _propose_ref("cuyas skills vas a cambiar"),
            ToolParam(
                name="skills",
                type="string",
                description=(
                    "Nombres de skill separados por comas, la lista completa "
                    "que debe quedar activa. Cadena vacía = ninguna."
                ),
                required=True,
            ),
        ),
    ),
    ToolSpec(
        name="console.propose_publish",
        kind="publish",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/clients/{client_ref}/agent",
        label="Proponer publicar una versión",
        description=(
            "Prepara la publicación de una versión concreta del agente y "
            "devuelve el diff contra la que está activa ahora. Publicar es un "
            "acto APARTE: crear o editar un borrador nunca lo publica, aunque "
            "el usuario diga «hazlo ya». Llama a esto solo cuando lo pida "
            "explícitamente, y avisa si no se ha probado nada en el "
            "playground: publicar es lo que pone el cambio delante de los "
            "clientes finales del partner."
        ),
        params=(
            _propose_ref("cuya versión vas a publicar"),
            ToolParam(
                name="version",
                type="integer",
                description=(
                    "Número de versión a publicar. Léelo de console.get_agent; "
                    "no supongas que es la última."
                ),
                required=True,
                minimum=1,
            ),
        ),
    ),
    ToolSpec(
        name="console.propose_channel_role",
        kind="channel_role",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/clients/{client_ref}/channels",
        label="Proponer el rol de un canal",
        description=(
            "Etiqueta un canal de WhatsApp como el del agente o el de "
            "notificaciones. Importa cuando el cliente tiene más de un número: "
            "con varios canales activos y ninguno etiquetado, la plataforma "
            "RECHAZA el envío en vez de adivinar. Llama a console.list_channels "
            "antes para leer los ids y los roles actuales."
        ),
        params=(
            _propose_ref("cuyo canal vas a etiquetar"),
            ToolParam(
                name="channel_id",
                type="string",
                description="Id del canal, tal y como lo devuelve console.list_channels.",
                required=True,
            ),
            ToolParam(
                name="role",
                type="string",
                description=(
                    "'agent' para el número por el que atiende el agente, "
                    "'notifications' para el de avisos salientes, cadena vacía "
                    "para quitarle el rol que tenga."
                ),
                required=True,
                enum=("agent", "notifications", ""),
            ),
        ),
    ),
    ToolSpec(
        name="console.propose_usage_alerts",
        kind="usage_alerts",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/usage/alerts",
        label="Proponer los avisos de consumo",
        description=(
            "Cambia el tope mensual de mensajes del partner y a quién se avisa "
            "al acercarse. Es del PARTNER entero, no de un cliente. Lee el "
            "estado actual antes: la lista de destinatarios que mandes "
            "sustituye a la anterior."
        ),
        params=(
            ToolParam(
                name="cap_messages_month",
                type="integer",
                description="Tope de mensajes al mes. 0 para quitar el tope.",
                minimum=0,
                maximum=1_000_000_000,
            ),
            ToolParam(
                name="recipients",
                type="string",
                description=(
                    "Correos separados por comas que reciben el aviso. La lista "
                    "completa: lo que no esté deja de recibirlo."
                ),
            ),
            ToolParam(
                name="enabled",
                type="boolean",
                description="Si los avisos están encendidos.",
            ),
        ),
    ),
    ToolSpec(
        name="console.propose_allocation",
        kind="allocation",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/wallet",
        label="Proponer el cupo de un cliente",
        description=(
            "Calcula el cambio de tope (cupo) de un cliente y lo deja pendiente "
            "de confirmación. No escribe: aplicar usa set_allocation bajo el "
            "partner del principal. Llama a esto cuando el usuario quiera "
            "asignar cupo por primera vez o cambiar el tope de un cliente que "
            "ya lo tiene; lee console.get_wallet y console.list_allocations "
            "antes para no proponer una suma que supere lo disponible. El "
            "cuerpo de aplicación solo lleva cap: el partner no viaja. No lo "
            "uses para recargar el cubo purchased ni para avisos de mensajes."
        ),
        params=(
            _propose_ref("cuyo cupo vas a cambiar"),
            ToolParam(
                name="cap",
                type="integer",
                description="Tope nuevo en tokens de cuota. Entero ≥ 0.",
                required=True,
                minimum=0,
            ),
        ),
        max_chars=4_000,
    ),
    ToolSpec(
        name="console.propose_model",
        kind="model",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/clients/{client_ref}/model",
        label="Proponer el modelo de un cliente",
        description=(
            "Calcula el cambio de modelo de respuesta de un cliente "
            "(Sol, Terra o Luna) y lo deja pendiente de confirmación. No "
            "escribe: aplicar usa PUT /console/clients/{ref}/model con "
            "solo model_id, bajo el partner del principal. Llama a esto "
            "cuando el usuario quiera elegir o cambiar el modelo con el "
            "que responde el agente. Lee console.list_models y "
            "console.get_client_model antes. El cuerpo de aplicación solo "
            "lleva model_id: el partner no viaja. No lo uses para "
            "classify, Companion, whisper, el cupo ni el prompt. No "
            "aceptes gpt-5.6 suelto: no es una fila del catálogo. Guía: "
            "Sol es el más capaz, Terra el día a día, Luna volumen."
        ),
        params=(
            _propose_ref("cuyo modelo vas a cambiar"),
            ToolParam(
                name="model_id",
                type="string",
                description=(
                    "Id LiteLLM verbatim del catálogo cerrado. Uno de "
                    "openai/gpt-5.6-sol, openai/gpt-5.6-terra, "
                    "openai/gpt-5.6-luna. No gpt-5.6."
                ),
                required=True,
                enum=RESPOND_MODEL_IDS,
            ),
        ),
        max_chars=4_000,
    ),
    ToolSpec(
        name="console.propose_knowledge",
        kind="knowledge",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/knowledge",
        label="Proponer un documento de conocimiento",
        description=(
            "Prepara añadir una URL al playbook del partner o al conocimiento de "
            "un cliente. scope es obligatorio: partner o client. Si es client, "
            "manda también client_ref. No escribe: aplicar usa POST /url del "
            "alcance (el archivo solo se sube desde la consola). El interrupt "
            "nombra el alcance. El cuerpo de aplicación nunca lleva partner_id. "
            "No lo uses para buscar en un índice: no hay kb.search."
        ),
        params=(
            ToolParam(
                name="scope",
                type="string",
                description="Alcance: partner (playbook) o client (KB de un cliente).",
                required=True,
                enum=("partner", "client"),
            ),
            ToolParam(
                name="url",
                type="string",
                description="URL http(s) pública a indexar.",
                required=True,
            ),
            ToolParam(
                name="title",
                type="string",
                description="Título opcional. Si falta, se usa la URL o el título de la página.",
            ),
            ToolParam(
                name="client_ref",
                type="string",
                description=(
                    "Referencia del cliente. Obligatoria si scope=client. La que "
                    "devuelve console.list_clients. Un ref ajeno es el mismo 404 "
                    "opaco que uno inexistente."
                ),
            ),
        ),
        max_chars=4_000,
    ),
    ToolSpec(
        name="console.propose_pack",
        kind="pack",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/clients/{client_ref}/workflow",
        label="Proponer un pack",
        description=(
            "Entrevista y propone un pack v1 (YAML): trigger cron o event, "
            "steps solo send_template, wait_reply, end, plantilla WhatsApp "
            "y hora en zona del partner. No escribe: aplicar usa PUT "
            "/console/clients/{ref}/workflow. Tú NUNCA aplicas solo. "
            "Camino conocido y cerrado → pack sin agente; abierto o mixto "
            "→ no pack en v1. El primer toque de WhatsApp es send_template "
            "(Art. 50), no un nodo extra. Lee console.get_workflow y "
            "console.list_templates antes. El cuerpo no lleva partner_id."
        ),
        params=(
            _propose_ref("cuyo pack vas a proponer"),
            ToolParam(
                name="trigger",
                type="string",
                description="cron (hora fija) o event.",
                required=True,
                enum=("cron", "event"),
            ),
            ToolParam(
                name="steps",
                type="string",
                description=(
                    "IDs cerrados separados por comas. Solo "
                    "send_template, wait_reply, end. El primero que envíe "
                    "tiene que ser send_template."
                ),
                required=True,
            ),
            ToolParam(
                name="template_id",
                type="string",
                description="Plantilla de WhatsApp si hay send_template.",
            ),
            ToolParam(
                name="hour",
                type="integer",
                description="Hora local del partner (0-23) si trigger=cron.",
                minimum=0,
                maximum=23,
            ),
            ToolParam(
                name="minute",
                type="integer",
                description="Minuto local (0-59) si trigger=cron.",
                minimum=0,
                maximum=59,
            ),
            ToolParam(
                name="timezone",
                type="string",
                description="Zona IANA para la UI. Se persiste UTC.",
            ),
            ToolParam(
                name="enabled",
                type="boolean",
                description="Si el pack queda activo.",
            ),
        ),
        max_chars=4_000,
    ),
    ToolSpec(
        name="console.propose_invite",
        kind="invite",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/team",
        label="Proponer invitar a alguien",
        description=(
            "Prepara la invitación de una persona al equipo del partner con un "
            "rol. NUNCA por encima del rol de quien te habla: si te piden "
            "invitar a alguien con más permisos que el propio usuario, dilo y "
            "no lo propongas. El correo se muestra enmascarado en la tarjeta "
            "de confirmación; eso es deliberado."
        ),
        params=(
            ToolParam(
                name="email",
                type="string",
                description="Correo de la persona a invitar.",
                required=True,
            ),
            ToolParam(
                name="role",
                type="string",
                description="Rol dentro del partner.",
                required=True,
                enum=("owner", "admin", "builder", "analyst", "billing"),
            ),
        ),
    ),
    # ── CO-08, §4 de CONTRACT-V2 ───────────────────────────────────────
    #
    # El Companion nunca cierra una conversación con un "no". La cierra con
    # un camino: o lo hace, o abre el camino para que alguien lo haga.
    #
    # Son ``propose`` como las nueve de arriba, y por el mismo motivo: nadie
    # manda un ticket a nombre del partner sin que el partner lo vea. La
    # única ``mutates`` del catálogo sigue siendo ``console.apply``
    # (garantía E4). ``path`` es lo que la propuesta LEE para componer el
    # expediente; el destino lo fija ``APPLY_ROUTES`` por el ``kind``.
    ToolSpec(
        name="support.request_help",
        kind="support_help",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/capabilities",
        label="Ofrecer abrir un ticket de soporte",
        description=(
            "Prepara un ticket para Auphere con el expediente que YA has leído "
            "en este turno: qué necesita la persona, qué comprobaste y qué "
            "alternativa hay. Llama a esto cuando topes con un límite real —una "
            "capacidad que no existe, un permiso que el rol no tiene, una cuota "
            "agotada, algo de la plataforma que falla— en vez de cerrar con un "
            "'no se puede': un 'no' deja a la persona igual de bloqueada que "
            "antes. Léete console.get_capabilities primero; sin ninguna lectura "
            "previa el ticket va sin expediente y se rechaza. No lo uses para "
            "pedir funcionalidad nueva: eso es support.request_capability."
        ),
        params=(
            ToolParam(
                name="topic",
                type="string",
                description=(
                    "Etiqueta estable del asunto, con familia: connector.*, "
                    "channel.*, capability.*, platform.*, quota.* o permission.* "
                    "(ej. connector.shopify, quota.clients). Es lo que permite "
                    "contar cuántos partners piden lo mismo; no escribas una "
                    "frase. Si usas la clave de una entrada de "
                    "console.get_capabilities, mejor: son el mismo espacio."
                ),
                required=True,
            ),
            ToolParam(
                name="need",
                type="string",
                description=(
                    "Qué necesita CONSEGUIR la persona, en una o dos frases y "
                    "con sus palabras. No lo que falla: soporte tiene que poder "
                    "leerlo sin conocer la conversación."
                ),
                required=True,
            ),
            ToolParam(
                name="client_ref",
                type="string",
                description=(
                    "Referencia del cliente afectado, si lo hay. Déjalo vacío "
                    "cuando el ticket sea del partner entero."
                ),
            ),
            ToolParam(
                name="alternative",
                type="string",
                description=(
                    "El camino intermedio que propones, con sus limitaciones, o "
                    "vacío si no hay ninguno. Di 'ninguna sin desarrollo' antes "
                    "que inventarte una."
                ),
            ),
            ToolParam(
                name="bridge",
                type="boolean",
                description=(
                    "true si 'alternative' es una solución puente que la persona "
                    "puede usar ya. El puente NO sustituye al ticket: se etiqueta "
                    "y el ticket se abre igual, porque un puente que nadie "
                    "registra se convierte en deuda invisible."
                ),
            ),
        ),
        max_chars=4_000,
    ),
    ToolSpec(
        name="support.request_capability",
        kind="support_capability",
        tool_class="propose",
        permission_policy="always_ask",
        path="/console/capabilities",
        label="Pedir una capacidad que no existe",
        description=(
            "Prepara una petición de funcionalidad para la hoja de ruta de "
            "Auphere. Llama a esto cuando lo que falta no es una incidencia sino "
            "algo que la plataforma no hace todavía —un conector, un canal, una "
            "capacidad— y quieras que cuente: se agregan por asunto, así que "
            "siete partners pidiendo lo mismo se ven. Comprueba antes con "
            "console.get_capabilities: si ya existe, ayúdale a usarlo, y si está "
            "fuera de alcance dile por qué en vez de abrir la petición. No hay "
            "compromiso de fecha y no lo insinúes."
        ),
        params=(
            ToolParam(
                name="topic",
                type="string",
                description=(
                    "Etiqueta estable de la capacidad pedida, con familia "
                    "(connector.shopify, channel.instagram, "
                    "capability.custom_reports). Es la clave con la que se "
                    "agregan las peticiones; no escribas una frase."
                ),
                required=True,
            ),
            ToolParam(
                name="need",
                type="string",
                description=(
                    "Para qué la quiere, en una o dos frases. El caso de uso "
                    "concreto vale más que el nombre del producto."
                ),
                required=True,
            ),
            ToolParam(
                name="client_ref",
                type="string",
                description=(
                    "Referencia del cliente que la necesita, si es de uno en "
                    "concreto. Vacío si es del partner."
                ),
            ),
            ToolParam(
                name="alternative",
                type="string",
                description=("Con qué se apaña mientras tanto, o vacío si no hay nada."),
            ),
            ToolParam(
                name="bridge",
                type="boolean",
                description=(
                    "true si 'alternative' es una solución puente usable ya. Se "
                    "etiqueta y la petición se abre igual."
                ),
            ),
        ),
        max_chars=4_000,
    ),
)


# ── ejecución (CO-04, §6.3) ────────────────────────────────────────────
#
# **Una sola puerta de escritura en todo el Companion.** Que sea una y no
# once es lo que hace verificable la garantía C4 (E4 en la Ola 2): no hay
# forma de añadir un camino de escritura por descuido, porque cualquier
# herramienta nueva que escribiera tendría que declararse ``mutates`` y el
# test la vería. Las dos de soporte de CO-08 no son la excepción: proponen.
#
# ``path`` es ``/console/companion/actions/{action_id}`` —el endpoint de
# lectura de la acción— y no el destino de la escritura: el destino lo decide
# el ``kind`` de la fila confirmada, no el modelo. El modelo no puede
# redirigir una acción a otro endpoint ni cambiando los argumentos.

APPLY_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="console.apply",
        tool_class="mutates",
        permission_policy="always_ask",
        path="/console/companion/actions/{action_id}",
        label="Aplicar una acción confirmada",
        description=(
            "Aplica una acción que la persona YA confirmó. Solo funciona con "
            "una acción en estado 'confirmed': con cualquier otra falla, y "
            "falla en el motor, no porque tú decidas no llamarla. No la uses "
            "para intentar aplicar algo que acabas de proponer — proponer no "
            "es confirmar, y entre las dos cosas hay una persona."
        ),
        params=(
            ToolParam(
                name="action_id",
                type="string",
                description="Identificador de la acción confirmada.",
                required=True,
            ),
        ),
        max_chars=4_000,
    ),
)


# ── prueba (CO-05, §7 de CONTRACT-V2) ──────────────────────────────────
#
# "Testear antes de disponibilizar". Un turno en seco contra el agente
# **borrador** —la versión ``staged``—, midiendo contra el tope del
# PLAYGROUND y no contra el del Companion: el gasto de probar lo consume el
# agente del cliente, no el Companion, y mezclar los dos medidores haría que
# probar mucho apagara el Companion.
#
# No es ``read`` porque hace un POST, y no es ``propose`` ni ``mutates``
# porque no cambia absolutamente nada del cliente. Tiene clase propia para
# que eso quede dicho en el dato y no en un comentario.
TRIAL_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="companion.run_playground_turn",
        path="/console/clients/{client_ref}/playground/threads/{thread_id}/runs",
        method="POST",
        label="Probando el borrador en el playground",
        description=(
            "Prueba el agente BORRADOR de un cliente mandándole uno o varios "
            "mensajes de prueba y devuelve, por cada uno, si respondió y cuánto "
            "tardó. Llama a esto ANTES de proponer una publicación, y siempre "
            "que acabes de cambiar el prompt, la política, las herramientas o "
            "las habilidades: es la única forma de saber si el cambio hace lo "
            "que la persona te pidió. No devuelve el texto de la respuesta del "
            "agente —para leerla hay que abrir el playground—, así que no cites "
            "lo que 'contestó': cita si pasó o no pasó cada comprobación. No lo "
            "uses para probar el agente ACTIVO: prueba siempre el borrador."
        ),
        params=(
            ToolParam(
                name=CLIENT_REF,
                type="string",
                description=(
                    "Referencia del cliente cuyo borrador quieres probar. La que "
                    "devuelve console.list_clients."
                ),
                required=True,
                in_path=True,
            ),
            ToolParam(
                name="probes",
                type="string",
                description=(
                    "Los mensajes de prueba, uno por línea, como se los escribiría "
                    "un cliente final. Máximo cinco. Escríbelos tú a partir de lo "
                    "que la persona quiere arreglar: si te pidió que no dé precios "
                    "por WhatsApp, pregunta un precio. Un mensaje de prueba que no "
                    "ejercita el cambio no prueba nada."
                ),
                required=True,
            ),
        ),
        tool_class="trial",
        max_chars=6_000,
    ),
)

ALL_TOOLS: tuple[ToolSpec, ...] = (*READ_TOOLS, *PROPOSE_TOOLS, *TRIAL_TOOLS, *APPLY_TOOLS)

TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in ALL_TOOLS}

#: Los ``kind`` del §3.1 del contrato —más ``allocation`` y ``model``—,
#: derivados del catálogo y no escritos a mano:
#: una herramienta ``propose`` sin ``kind`` no se puede construir, así que
#: la lista no puede desincronizarse. La lista de PROHIBIDOS del §6.5 no
#: cambia: no hay ``kind`` para borrar clientes, tocar facturación, rotar
#: claves ni desactivar la revelación de IA, y no se añade uno.
ACTION_KINDS: tuple[str, ...] = tuple(t.kind for t in PROPOSE_TOOLS if t.kind is not None)


def tool_specs(*, mode: str = "build") -> list[dict[str, Any]]:
    """El catálogo en el formato de herramientas del proveedor.

    ``mode`` es el del hilo (``consult`` / ``build``), y es del usuario, no
    del modelo: en *Consultar* se publican solo las lecturas, así que el
    modelo no puede proponer un cambio ni por descuido ni porque alguien se
    lo pida dentro de un texto. En *Construir* se publican las tres clases.
    """
    tools = READ_TOOLS if mode == "consult" else ALL_TOOLS
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.json_schema(),
            },
        }
        for t in tools
    ]


__all__ = [
    "ACTION_KINDS",
    "ALL_TOOLS",
    "APPLY_TOOLS",
    "CLIENT_REF",
    "PROPOSE_TOOLS",
    "READ_TOOLS",
    "TOOLS_BY_NAME",
    "PermissionPolicy",
    "ToolClass",
    "ToolParam",
    "ToolSpec",
    "tool_specs",
]
