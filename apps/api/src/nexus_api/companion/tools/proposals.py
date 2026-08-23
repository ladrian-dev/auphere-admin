"""El cálculo de una propuesta, por ``kind`` (CO-04, §6.2).

Una propuesta es **lectura y aritmética**. Se lee el estado actual por los
mismos routers ``/console/*`` que usa la interfaz, se calcula qué cambiaría,
y se devuelve todo junto: previsualización, diff, impacto, riesgo,
reversibilidad, el hash del estado del que depende y la petición exacta que
la aplicaría. Nada de esto escribe.

Las tres cosas que hacen que esto no sea "una función que arma un JSON"
--------------------------------------------------------------------

- **El destino de la escritura lo fija el ``kind``, no el modelo.**
  :data:`APPLY_ROUTES` es un mapa cerrado de nueve entradas. Un modelo que
  quisiera redirigir una acción a ``/console/keys`` no tiene por dónde: el
  campo no existe en ningún argumento. Es lo que hace estrecha la superficie
  de escritura del Companion, y hay un test que recorre ese mapa buscando
  cualquier ruta de la lista prohibida del §6.5.

- **El ``state_hash`` es el CAS del Companion.** Los endpoints ``/console/*``
  no tienen comparación-e-intercambio; hoy no existe. Así que la propuesta
  guarda la huella de lo que leyó y ``resume:confirm`` la recalcula: si otra
  persona publicó una versión mientras esta decidía, sale 412 y se vuelve a
  proponer con datos frescos. Qué entra en el hash está en §3.5 del contrato
  y se decide aquí, por ``kind``, con una regla: entra lo que, si cambia,
  **invalida el diff que el humano vio**. Ni un byte más — un hash de todo el
  recurso daría 412 espurios cada vez que alguien toca un ``last_seen_at``.

- **El correo de un tercero se enmascara en ORIGEN.** No en la interfaz: si
  saliera entero del backend, ya estaría en el log durable, en el contexto
  del modelo y en la transcripción persistida.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import httpx

from nexus_api.companion.tools.errors import ToolError, translate_status

# ── el mapa cerrado de escritura ───────────────────────────────────────
#
# Verificado contra ``app.routes``: cinco de las nueve rutas difieren de la
# tabla del §3.1 del contrato, que delega esa columna en el Agente B. Manda
# la ruta real; el desvío está anotado en ``docs/companion/PLAN-CO-04.md``
# §D1. A y C no consumen esa columna, así que no es cambio de contrato.

ApplyMethod = Literal["POST", "PUT", "PATCH"]

APPLY_ROUTES: dict[str, tuple[ApplyMethod, str]] = {
    # No existe ``PUT …/agent/draft``: en esta plataforma el borrador ES una
    # versión ``staged``, y se crea apilando una versión nueva.
    "client": ("POST", "/console/clients"),
    "prompt": ("POST", "/console/clients/{client_ref}/agent/versions"),
    "policy": ("PUT", "/console/clients/{client_ref}/agent/settings"),
    "tools": ("PUT", "/console/clients/{client_ref}/tools"),
    "skills": ("PUT", "/console/clients/{client_ref}/skills"),
    # La versión va en la RUTA, así que la propuesta tiene que fijarla al
    # proponer. Es lo correcto además de lo obligado: publicar "la última"
    # cuando alguien apiló otra entremedias es justo el fallo que el
    # ``state_hash`` existe para atrapar.
    "publish": ("POST", "/console/clients/{client_ref}/agent/versions/{version}/publish"),
    "channel_role": ("PATCH", "/console/clients/{client_ref}/channels/{channel_id}/role"),
    "usage_alerts": ("PUT", "/console/usage/alerts"),
    "allocation": ("PUT", "/console/clients/{client_ref}/allocation"),
    "model": ("PUT", "/console/clients/{client_ref}/model"),
    "knowledge": ("POST", "/console/knowledge/url"),
    "pack": ("PUT", "/console/clients/{client_ref}/workflow"),
    "invite": ("POST", "/console/team/invitations"),
    # CO-08 (§4.1 de CONTRACT-V2). Los dos ``kind`` de soporte aplican por el
    # MISMO endpoint; lo que los distingue es ``category`` dentro del cuerpo,
    # que la propuesta fija y el modelo no puede cambiar después.
    "support_help": ("POST", "/console/support/tickets"),
    "support_capability": ("POST", "/console/support/tickets"),
}

#: Acciones que no se pueden deshacer desde la consola. Viaja al cajón dentro
#: de ``plan.proposed`` y decide el color de la tarjeta.
IRREVERSIBLE_KINDS: frozenset[str] = frozenset({"client"})

#: Jerarquía de roles del partner, para el techo de C6. ``analyst`` y
#: ``billing`` empatan a propósito: son alcances distintos, no niveles.
ROLE_RANK: dict[str, int] = {
    "owner": 4,
    "admin": 3,
    "builder": 2,
    "analyst": 1,
    "billing": 1,
}

#: Campo plano del modelo → ruta dentro de ``ConsolePolicy``.
#:
#: El objeto real está anidado y el esquema de una herramienta solo admite
#: escalares. En vez de pedirle al modelo que redacte JSON anidado —que es
#: justo donde se equivoca, y donde el error se convierte en un 422 que no
#: sabe corregir— se acepta lo plano y se compone aquí.
#:
#: **``ai_disclosure`` no está y no se añade.** El §6.5 prohíbe desactivar la
#: revelación de IA; dejar el campo expuesto "solo para activarla" sería
#: dejar la palanca al alcance de una inyección de prompt para nada, porque
#: el valor por defecto ya es ``true``.
POLICY_FIELDS: dict[str, tuple[str, ...]] = {
    "objective": ("objective",),
    "primary_language": ("languages", "primary"),
    "timezone": ("schedule", "timezone"),
    "closed_message": ("schedule", "closed_message"),
    "escalation_enabled": ("escalation", "enabled"),
    "handoff_message": ("escalation", "handoff_message"),
}


@dataclass(frozen=True)
class Proposal:
    """Un cambio calculado y no aplicado.

    Es lo que el nodo ``plan`` del grafo persiste en ``companion.actions`` y
    lo que la interfaz pinta en la tarjeta de confirmación.
    """

    kind: str
    title: str
    #: Objeto libre por ``kind`` (§3.4). Sin propiedades declaradas: el
    #: recorrido del OpenAPI no puede encontrar nada dentro.
    preview: dict[str, Any]
    #: Operaciones ``{op, line, before?, after?}``. ``None`` cuando el
    #: ``kind`` no tiene un diff textual que enseñar.
    diff: list[dict[str, Any]] | None
    impact: list[dict[str, Any]]
    risk: str
    reversible: bool
    state_hash: str
    #: La petición exacta que aplicaría esto. Se guarda con la acción y se
    #: relee al aplicar: el modelo no vuelve a intervenir.
    apply_method: str
    apply_path: str
    apply_body: dict[str, Any] | None
    #: Lo que ``verify`` espera encontrar al releer. Nombres estables en
    #: inglés; los valores, cadenas siempre (§2.5 del contrato).
    expectations: dict[str, str] = field(default_factory=dict)
    #: Referencia del cliente afectado, o ``None`` si la acción es del
    #: partner entero (avisos de consumo, invitaciones).
    client_ref: str | None = None
    #: Los argumentos exactos con los que el modelo la pidió. Se guardan para
    #: poder **recalcular el hash** al confirmar: revalidar es rehacer la
    #: propuesta con datos frescos y comparar, y sin los argumentos originales
    #: no hay nada que rehacer. No vuelven al modelo ni salen por el stream.
    propose_args: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        """Lo que se guarda en ``companion.actions.payload``."""
        return {
            "title": self.title,
            "preview": self.preview,
            "impact": self.impact,
            "risk": self.risk,
            "reversible": self.reversible,
            "client_ref": self.client_ref,
            "apply": {
                "method": self.apply_method,
                "path": self.apply_path,
                "body": self.apply_body,
            },
            "expectations": self.expectations,
            "propose_args": self.propose_args,
        }


# ── helpers deterministas ──────────────────────────────────────────────


def canonical_hash(payload: Any) -> str:
    """SHA-256 hexadecimal de un JSON canónico.

    ``sort_keys`` y separadores compactos para que el mismo estado dé
    siempre el mismo hash: dos serializaciones distintas del mismo objeto
    serían un 412 inventado.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def short_digest(text: str) -> str:
    """Huella corta y legible de un texto largo. Va en ``expected``/``actual``
    de la verificación: comparar dos prompts de 8.000 caracteres a ojo en una
    tabla no es verificar nada."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


#: Cuántas líneas de contexto acompañan a cada cambio del diff. Tres es lo
#: que usa ``diff -u`` y lo que la gente lee sin pensar.
DIFF_CONTEXT_LINES = 3

#: Tope de operaciones del diff. Un prompt reescrito entero produce cientos y
#: la tarjeta se vuelve ilegible; además el diff viaja por el log durable.
DIFF_MAX_OPS = 400


def line_diff(before: str, after: str) -> list[dict[str, Any]]:
    """Diff línea a línea en la forma del §2.3 del contrato.

    ``op`` ∈ ``add | del | ctx``; ``ctx`` lleva ``before`` y ``after``
    iguales. La numeración es la del texto NUEVO para ``add`` y ``ctx``, y la
    del viejo para ``del`` — que es lo que hace que un lector pueda ir a la
    línea del editor y encontrarla.
    """
    old = (before or "").splitlines()
    new = (after or "").splitlines()
    ops: list[dict[str, Any]] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            span = list(range(i1, i2))
            # Solo el contexto pegado a un cambio; el resto no aporta y
            # engorda el payload.
            keep = set(span[:DIFF_CONTEXT_LINES]) | set(span[-DIFF_CONTEXT_LINES:])
            for idx in span:
                if idx not in keep:
                    continue
                line = old[idx]
                ops.append(
                    {"op": "ctx", "line": j1 + (idx - i1) + 1, "before": line, "after": line}
                )
            continue
        for idx in range(i1, i2):
            ops.append({"op": "del", "line": idx + 1, "before": old[idx]})
        for idx in range(j1, j2):
            ops.append({"op": "add", "line": idx + 1, "after": new[idx]})
    if len(ops) > DIFF_MAX_OPS:
        cut = len(ops) - DIFF_MAX_OPS
        ops = ops[:DIFF_MAX_OPS]
        ops.append({"op": "ctx", "line": 0, "before": f"… y {cut} cambios más", "after": ""})
    return ops


_EMAIL = re.compile(r"^([^@]+)@(.+)$")

#: Referencia técnica de una plantilla de arranque, tal y como la acepta el
#: router (``aesthetic_clinic_v1``). "Clínica estética" no lo es.
_SEED_REF = re.compile(r"^[a-z0-9_]+$")


def mask_email(email: str) -> str:
    """``maria@facelad.com`` → ``m…a@facelad.com``.

    En ORIGEN, no en la interfaz. Un correo completo que sale del backend ya
    está en el log durable de Redis, en el contexto del modelo y en la
    transcripción persistida del hilo; enmascararlo después es enmascararlo
    en el único sitio donde ya no importa.
    """
    match = _EMAIL.match((email or "").strip())
    if match is None:
        return "…"
    local, domain = match.group(1), match.group(2)
    if len(local) <= 2:
        return f"{local[:1]}…@{domain}"
    return f"{local[0]}…{local[-1]}@{domain}"


def split_list(raw: str | None) -> list[str]:
    """Una cadena separada por comas → lista limpia y sin repetidos.

    El modelo escribe listas como texto porque el esquema de parámetros solo
    admite escalares (es lo que mejor toleran todos los proveedores). El
    orden se conserva: es el que la persona verá en la tarjeta.
    """
    if not raw:
        return []
    return list(dict.fromkeys(p.strip() for p in raw.split(",") if p.strip()))


def _impact(key: str, value: Any, severity: str = "info") -> dict[str, Any]:
    return {"key": key, "value": str(value), "severity": severity}


class ProposalRefused(Exception):
    """La propuesta no se puede construir, y el motivo es del modelo.

    Lleva un :class:`ToolError` porque lo que ve el modelo tiene que decirle
    qué corregir. No es un fallo de plataforma: es un "esto no, y por esto".
    """

    def __init__(self, error: ToolError) -> None:
        super().__init__(error.message)
        self.error = error


class IntakeRequired(Exception):
    """Falta información que **solo tiene el cliente** (§7.1).

    Distinto de :class:`ProposalRefused`: ahí el modelo se equivocó y puede
    corregirse solo; aquí no hay nada que corregir, hay que preguntar. Por
    eso sale por un evento propio (``intake.missing``) que el cajón pinta
    como chips respondibles, y no como un error de herramienta.
    """

    def __init__(self, slots: list[dict[str, Any]]) -> None:
        super().__init__(f"faltan {len(slots)} datos")
        self.slots = slots


#: Lo que hay que saber ANTES de dar de alta un cliente, y por qué.
#:
#: ``forbidden_behaviour`` es obligatorio a propósito y es el que justifica
#: que esto exista: es el campo que nadie escribe y el que causa los
#: incidentes. Preguntarlo siempre cuesta diez segundos; no preguntarlo
#: cuesta una conversación con el cliente final de un cliente.
CLIENT_INTAKE_SLOTS: tuple[dict[str, Any], ...] = (
    {
        "key": "vertical",
        "label": "A qué se dedica el cliente",
        "why": "Decide la plantilla de arranque y las herramientas que tienen sentido.",
        "examples": ["Clínica estética", "Barbería", "Inmobiliaria"],
        "required": True,
    },
    {
        "key": "timezone",
        "label": "Zona horaria del cliente",
        "why": "Sin ella el horario de atención se calcula mal y el agente responde a deshora.",
        "examples": ["America/Caracas", "Europe/Madrid"],
        "required": True,
    },
    {
        "key": "language",
        "label": "Idioma principal de atención",
        "why": "Es en el que hablará con los clientes finales por defecto.",
        "examples": ["es", "en", "pt"],
        "required": True,
    },
    {
        "key": "forbidden_behaviour",
        "label": "Qué NO debe hacer el agente",
        "why": "Es el campo que nadie escribe y el que causa los incidentes.",
        "examples": ["No dar precios por WhatsApp", "No agendar sin seña"],
        "required": True,
    },
)


# ── el constructor por ``kind`` ────────────────────────────────────────


def _parse_fields(raw: Any) -> dict[str, str]:
    """``address=Av. Principal 123`` por línea → ``{"address": "…"}``.

    Se parte por el PRIMER ``=`` a propósito: una dirección puede llevar
    signos de igual y partir por todos convertiría el valor en basura.
    """
    fields: dict[str, str] = {}
    for line in str(raw or "").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and value.strip():
            fields[key.strip()] = value.strip()
    return fields


def _field_value(args: dict[str, Any], placeholder_key: str) -> str:
    """El valor de un placeholder, se haya escrito con clave completa o corta.

    El modelo ve ``tenant.address`` en el mensaje de intake y es lo que suele
    devolver; pero también escribe ``address`` a secas. Aceptar las dos formas
    cuesta una línea y evita un bucle en el que la propuesta pide siempre lo
    mismo porque la clave no coincide por un prefijo.
    """
    for candidate in (placeholder_key, _arg_name(placeholder_key)):
        value = str(args.get(candidate) or "").strip()
        if value:
            return value
    return ""


def _arg_name(placeholder_key: str) -> str:
    """``tenant.address`` → ``address``.

    El modelo escribe argumentos planos; la plantilla los nombra con espacio
    de nombres. Traducir aquí evita pedirle al modelo que adivine un punto en
    medio del nombre de un parámetro.
    """
    return placeholder_key.rsplit(".", 1)[-1]


def _trial_warning(trial: Any, target_version: int) -> dict[str, Any]:
    """Las tres claves de aviso del §7.1 del contrato (CO-05).

    **Avisan, no prohíben.** El usuario puede publicar sin probar: se le dice,
    queda en la fila de la acción y en la auditoría, y se publica. Prohibirlo
    convertiría la prueba en un peaje que la gente aprende a rodear — y quien
    lo rodea deja de leer el aviso.

    Tres estados distintos y tres avisos distintos, porque la diferencia
    importa:

    - ``not_tried`` — nadie probó nada en esta conversación.
    - ``trial_failed`` — se probó y algún mensaje no obtuvo respuesta.
    - ``tried_active_only`` — se probó, pero lo que corrió fue la versión ya
      activa, **no la que se va a publicar**. Es el estado honesto por
      defecto mientras el playground no sepa correr un borrador: decir
      "probado" a secas sería exactamente la afirmación sin respaldo que R1
      existe para impedir.
    """
    if trial is None:
        return {"trial_ran": False, "trial_ok": None, "warning_key": "not_tried"}
    ok = bool(getattr(trial, "ok", False))
    tested = getattr(trial, "tested_version", None)
    if not ok:
        return {"trial_ran": True, "trial_ok": False, "warning_key": "trial_failed"}
    if tested is None or int(tested) != int(target_version):
        return {"trial_ran": True, "trial_ok": True, "warning_key": "tried_active_only"}
    return {"trial_ran": True, "trial_ok": True, "warning_key": None}


@dataclass
class ProposalBuilder:
    """Lee por HTTP en proceso y construye la propuesta.

    ``read`` es la función de lectura que le pasa el ejecutor: la misma que
    usan las herramientas de CO-02, con el sujeto puesto. Se inyecta en vez
    de importarse para que este módulo se pueda probar sin levantar la app.
    """

    read: Any  # Callable[[str, dict], Awaitable[httpx.Response]]
    #: Las etiquetas del catálogo de herramientas de las lecturas YA hechas
    #: en este turno. Las pone el ejecutor, no el modelo (CO-08 §4.2): es lo
    #: que convierte el expediente de un ticket en algo verificable, con la
    #: misma procedencia que sostiene R1. Vacío para los nueve ``kind`` de
    #: CO-04, que no lo usan.
    checked: tuple[str, ...] = ()
    #: Pruebas hechas en este turno, por referencia de cliente (CO-05). Las
    #: pone el ejecutor. Solo las lee ``_publish``, y solo para **avisar**:
    #: publicar sin haber probado sigue siendo posible a propósito.
    trials: dict[str, Any] = field(default_factory=dict)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response: httpx.Response = await self.read(path, params or {})
        if response.status_code >= 400:
            raise ProposalRefused(_translate(response, path))
        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - el router siempre da JSON
            raise ProposalRefused(
                ToolError("unavailable", f"La lectura de {path} no devolvió datos usables.")
            ) from exc

    async def build(self, kind: str, args: dict[str, Any]) -> Proposal:
        handler = getattr(self, f"_{kind}", None)
        if handler is None:  # pragma: no cover - el catálogo fija los nueve
            raise ProposalRefused(ToolError("unknown_tool", f"No sé proponer un {kind!r}."))
        proposal: Proposal = await handler(args)
        # Los argumentos se guardan una sola vez, aquí, en vez de en los nueve
        # constructores: uno que se olvidara dejaría una acción que no se
        # puede revalidar y que por tanto se confirmaría con datos viejos.
        return replace(proposal, propose_args=dict(args))

    # ── client ─────────────────────────────────────────────────────────

    async def _template_placeholders(self, vertical: str) -> list[dict[str, Any]]:
        """Los placeholders que declara la plantilla del vertical.

        Se leen del mismo endpoint que ya usa ``console.get_prompt_library``,
        así que no hay superficie nueva y la lectura va con el sujeto puesto.
        Si la plantilla no está, se devuelve vacío: el alta sin plantilla es
        válida y no debe bloquearse por no encontrar una lista.
        """
        try:
            listing = await self._get("/console/seed-templates")
        except ProposalRefused:
            return []
        for template in listing if isinstance(listing, list) else []:
            if str(template.get("name")) == vertical:
                placeholders = template.get("placeholders") or []
                return [p for p in placeholders if isinstance(p, dict)]
        return []

    async def _template_keys(self, vertical: str) -> list[str]:
        return [str(p.get("key")) for p in await self._template_placeholders(vertical)]

    async def _template_slots(self, vertical: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        """Lo que la plantilla exige y el modelo todavía no ha dado.

        Los ``key`` son los de la plantilla (``tenant.address``), no los cinco
        fijos del §3.3 del contrato. La interfaz cae a ``label``/``why`` para
        una clave que no conoce, que es exactamente el caso previsto.
        """
        slots: list[dict[str, Any]] = []
        for placeholder in await self._template_placeholders(vertical):
            if not placeholder.get("required"):
                continue
            key = str(placeholder.get("key") or "")
            if not key or _field_value(args, key):
                continue
            example = placeholder.get("example")
            slots.append(
                {
                    "key": key,
                    "label": str(placeholder.get("label") or key),
                    "why": (
                        "La plantilla de este vertical lo necesita para redactar "
                        "el prompt. Sin este dato el alta falla al aplicarse."
                    ),
                    "examples": [str(example)] if example else [],
                    "required": True,
                }
            )
        return slots

    async def _client(self, args: dict[str, Any]) -> Proposal:
        ref = str(args["client_ref"]).strip()

        # El expediente PRIMERO, antes de gastar dos lecturas: si falta algo
        # que solo sabe el cliente, no hay propuesta que calcular. El §7.1 es
        # explícito en que el Companion no avanza a planificar con campos
        # vacíos — rellenarlos con un valor plausible es el fallo caro.
        missing = [
            slot for slot in CLIENT_INTAKE_SLOTS if not str(args.get(slot["key"]) or "").strip()
        ]
        if missing:
            raise IntakeRequired([dict(s) for s in missing])

        me = await self._get("/console/me")
        quota = me.get("quota") or {}
        used = int(quota.get("used_clients") or 0)
        limit = int(quota.get("max_clients") or 0)

        listing = await self._get("/console/clients", {"limit": 200})
        existing = {str(c.get("external_client_ref")) for c in (listing.get("clients") or [])}
        if ref in existing:
            raise ProposalRefused(
                ToolError(
                    "already_exists",
                    f"Ya hay un cliente con la referencia {ref!r} bajo este partner. "
                    "Elige otra referencia o dile al usuario que ese cliente ya existe.",
                )
            )
        if limit and used >= limit:
            raise ProposalRefused(
                ToolError(
                    "quota_exhausted",
                    f"El partner ya usa {used} de {limit} clientes. No queda cuota, "
                    "así que el alta fallaría. Dilo y sugiere contactar con Auphere.",
                )
            )

        name = str(args["name"]).strip()
        timezone = str(args["timezone"]).strip()
        language = str(args["language"]).strip()
        vertical = str(args["vertical"]).strip()
        forbidden = str(args["forbidden_behaviour"]).strip()

        body: dict[str, Any] = {
            "external_client_ref": ref,
            "name": name,
            "timezone": timezone,
            # Lo que el agente NO debe hacer viaja con el alta, no en una
            # nota aparte: si se queda fuera del aprovisionamiento, se
            # pierde justo el dato por el que se preguntó.
            "placeholders": {"language": language, "forbidden_behaviour": forbidden},
        }
        if _SEED_REF.match(vertical):
            # El router solo acepta la referencia técnica de una plantilla
            # (``aesthetic_clinic_v1``). Cuando el usuario dice "clínica
            # estética" eso NO es una referencia: se conserva para que la
            # persona lo vea en la tarjeta y el alta va sin plantilla, en vez
            # de fallar con un 422 que nadie pidió.
            body["seed_template"] = vertical
            # Y cada plantilla pide LO SUYO además de los cinco campos fijos
            # del §7.1: la de clínica estética quiere la dirección, otra
            # querrá otra cosa. Se pregunta ANTES de proponer, porque el
            # camino contrario ya se probó y termina en un 422
            # ``missing placeholder: tenant.address`` **después** de que la
            # persona haya confirmado un alta irreversible. Preguntar es
            # barato; confirmar algo que va a fallar, no.
            args = {**args, **_parse_fields(args.get("template_fields"))}
            extra = await self._template_slots(vertical, args)
            if extra:
                raise IntakeRequired(extra)
            for slot_key in await self._template_keys(vertical):
                value = _field_value(args, slot_key)
                if value:
                    body["placeholders"][slot_key] = value

        return Proposal(
            kind="client",
            title=f"Dar de alta a {name}",
            preview={
                "name": name,
                "client_ref": ref,
                "vertical": vertical,
                "timezone": timezone,
                "language": language,
                "quota_used": used,
                "quota_max": limit,
            },
            diff=None,
            impact=[
                _impact("quota_after", f"{used + 1}/{limit}" if limit else str(used + 1)),
                # No es un adorno: el alta no se puede deshacer desde la
                # consola, y quien confirma tiene que verlo antes de pulsar.
                _impact("irreversible", "true", "danger"),
            ],
            risk="high",
            reversible=False,
            state_hash=canonical_hash({"used": used, "max": limit, "ref_taken": False}),
            apply_method=APPLY_ROUTES["client"][0],
            apply_path=APPLY_ROUTES["client"][1],
            apply_body=body,
            expectations={"client_exists": "true", "client_ref": ref},
            client_ref=ref,
        )

    # ── prompt ─────────────────────────────────────────────────────────

    async def _prompt(self, args: dict[str, Any]) -> Proposal:
        ref = str(args["client_ref"])
        prompt = str(args["system_prompt"])
        if not prompt.strip():
            raise ProposalRefused(
                ToolError(
                    "bad_arguments",
                    "El prompt no puede quedar vacío. Manda el texto completo del "
                    "prompt nuevo, no un fragmento.",
                )
            )
        bundle = await self._get(f"/console/clients/{ref}/agent")
        base = _editable_version(bundle)
        before = str((base or {}).get("system_prompt") or "")
        base_version = int((base or {}).get("version") or 0)

        ops = line_diff(before, prompt)
        added = sum(1 for o in ops if o["op"] == "add")
        removed = sum(1 for o in ops if o["op"] == "del")

        return Proposal(
            kind="prompt",
            title=f"Ajustar el prompt de {ref}",
            preview={
                "client_ref": ref,
                "summary": f"{added} líneas añadidas, {removed} eliminadas",
                "base_version": base_version or None,
            },
            diff=ops,
            impact=[
                _impact("lines_added", added),
                _impact("lines_removed", removed),
                # Lo que más se malinterpreta de este cambio: NO sale a
                # producción. Decirlo aquí evita el "creía que ya estaba".
                _impact("publishes", "false"),
            ],
            risk="medium" if removed else "low",
            reversible=True,
            state_hash=canonical_hash(
                {"base_version": base_version, "prompt_sha": short_digest(before)}
            ),
            apply_method=APPLY_ROUTES["prompt"][0],
            apply_path=APPLY_ROUTES["prompt"][1].format(client_ref=ref),
            apply_body={"system_prompt": prompt},
            expectations={"draft_prompt": short_digest(prompt)},
            client_ref=ref,
        )

    # ── policy ─────────────────────────────────────────────────────────

    async def _policy(self, args: dict[str, Any]) -> Proposal:
        ref = str(args["client_ref"])
        current = await self._get(f"/console/clients/{ref}/agent/settings")
        settings = dict(current.get("settings") or {})
        version = current.get("version")

        changes: list[dict[str, Any]] = []
        merged = json.loads(json.dumps(settings))  # copia profunda barata
        for name, path in POLICY_FIELDS.items():
            if name not in args or args[name] is None:
                continue
            value = args[name]
            old = _dig(settings, path)
            if old == value:
                continue
            _plant(merged, path, value)
            changes.append({"field": ".".join(path), "before": old, "after": value})

        if not changes:
            raise ProposalRefused(
                ToolError(
                    "no_change",
                    "Ninguno de los campos que mandaste cambia nada: ya están así. "
                    "Dilo y no propongas la acción.",
                )
            )

        ops = [
            {"op": "del", "line": i + 1, "before": f"{c['field']}: {c['before']!r}"}
            for i, c in enumerate(changes)
        ] + [
            {"op": "add", "line": i + 1, "after": f"{c['field']}: {c['after']!r}"}
            for i, c in enumerate(changes)
        ]

        return Proposal(
            kind="policy",
            title=f"Cambiar la política de {ref}",
            preview={
                "client_ref": ref,
                "summary": ", ".join(c["field"] for c in changes),
            },
            diff=ops,
            impact=[_impact("fields_changed", len(changes)), _impact("publishes", "false")],
            risk="low",
            reversible=True,
            state_hash=canonical_hash({"version": version, "settings": settings}),
            apply_method=APPLY_ROUTES["policy"][0],
            apply_path=APPLY_ROUTES["policy"][1].format(client_ref=ref),
            apply_body={"settings": merged},
            expectations={"policy": canonical_hash(merged)[:12]},
            client_ref=ref,
        )

    # ── tools / skills ─────────────────────────────────────────────────

    async def _tools(self, args: dict[str, Any]) -> Proposal:
        return await self._whitelist(
            args,
            kind="tools",
            arg="tools",
            path_tpl="/console/clients/{ref}/tools",
            collection="tools",
        )

    async def _skills(self, args: dict[str, Any]) -> Proposal:
        return await self._whitelist(
            args,
            kind="skills",
            arg="skills",
            path_tpl="/console/clients/{ref}/skills",
            collection="skills",
        )

    async def _whitelist(
        self,
        args: dict[str, Any],
        *,
        kind: str,
        arg: str,
        path_tpl: str,
        collection: str,
    ) -> Proposal:
        """``tools`` y ``skills`` son la misma forma: una lista blanca que se
        sustituye entera sobre el borrador. Un solo camino y un solo sitio
        donde equivocarse."""
        ref = str(args["client_ref"])
        wanted = split_list(args.get(arg))
        current = await self._get(path_tpl.format(ref=ref))
        rows = current.get(collection) or []
        available = {str(r.get("name")) for r in rows}
        enabled = sorted(str(r.get("name")) for r in rows if r.get("enabled"))

        unknown = [n for n in wanted if n not in available]
        if unknown:
            raise ProposalRefused(
                ToolError(
                    "bad_arguments",
                    f"No existen en el catálogo de este cliente: {', '.join(unknown)}. "
                    f"Lee las disponibles antes de proponer y usa los nombres exactos.",
                )
            )

        turning_on = sorted(set(wanted) - set(enabled))
        turning_off = sorted(set(enabled) - set(wanted))
        if not turning_on and not turning_off:
            raise ProposalRefused(
                ToolError(
                    "no_change",
                    f"Esa lista de {collection} es exactamente la que ya está activa. "
                    "Dilo y no propongas la acción.",
                )
            )

        ops = [{"op": "add", "line": i + 1, "after": n} for i, n in enumerate(turning_on)]
        ops += [{"op": "del", "line": i + 1, "before": n} for i, n in enumerate(turning_off)]

        return Proposal(
            kind=kind,
            title=f"Cambiar {collection} de {ref}",
            preview={
                "client_ref": ref,
                "summary": (
                    f"{len(turning_on)} activadas, {len(turning_off)} desactivadas, "
                    f"{len(wanted)} en total"
                ),
            },
            diff=ops,
            impact=[
                _impact("enabled_after", len(wanted)),
                # Desactivar es lo que rompe algo que hoy funciona; activar,
                # como mucho, no se usa. La severidad lo dice.
                _impact("turning_off", len(turning_off), "warn" if turning_off else "info"),
                _impact("publishes", "false"),
            ],
            risk="medium" if turning_off else "low",
            reversible=True,
            state_hash=canonical_hash({"version": current.get("version"), "enabled": enabled}),
            apply_method=APPLY_ROUTES[kind][0],
            apply_path=APPLY_ROUTES[kind][1].format(client_ref=ref),
            apply_body={collection: wanted},
            expectations={f"{collection}_enabled": str(len(wanted))},
            client_ref=ref,
        )

    # ── publish ────────────────────────────────────────────────────────

    async def _publish(self, args: dict[str, Any]) -> Proposal:
        ref = str(args["client_ref"])
        target_version = int(args["version"])
        bundle = await self._get(f"/console/clients/{ref}/agent")
        versions = {int(v["version"]): v for v in (bundle.get("versions") or [])}
        active_version = bundle.get("active_version")

        target = versions.get(target_version)
        if target is None:
            raise ProposalRefused(
                ToolError(
                    "bad_arguments",
                    f"El cliente {ref} no tiene una versión {target_version}. "
                    f"Las que hay: {', '.join(str(v) for v in sorted(versions)) or 'ninguna'}.",
                )
            )
        if active_version is not None and int(active_version) == target_version:
            raise ProposalRefused(
                ToolError(
                    "no_change",
                    f"La versión {target_version} ya es la activa. No hay nada que publicar.",
                )
            )

        active = versions.get(int(active_version)) if active_version is not None else None
        before = str((active or {}).get("system_prompt") or "")
        after = str(target.get("system_prompt") or "")

        return Proposal(
            kind="publish",
            title=f"Publicar la v{target_version} de {ref}",
            preview={
                "client_ref": ref,
                "from_version": active_version,
                "to_version": target_version,
                # Honesto por obligación: en la Ola 1 el Companion no sabe
                # ejecutar evals (eso es CO-05/CO-07), así que decir otra cosa
                # sería prometer una garantía que no hay.
                "evals_run": False,
                "evals_warning": "No se ejecutó ninguna evaluación sobre esta versión.",
                **_trial_warning(self.trials.get(ref), target_version),
            },
            diff=line_diff(before, after),
            impact=[
                _impact("from_version", active_version if active_version is not None else "—"),
                _impact("to_version", target_version),
                _impact("live_for_end_customers", "true", "warn"),
            ],
            risk="high",
            reversible=True,  # hay rollback a la versión anterior
            state_hash=canonical_hash(
                {
                    "active_version": active_version,
                    "target_version": target_version,
                    "target_prompt_sha": short_digest(after),
                }
            ),
            apply_method=APPLY_ROUTES["publish"][0],
            apply_path=APPLY_ROUTES["publish"][1].format(client_ref=ref, version=target_version),
            apply_body=None,
            expectations={"active_version": str(target_version)},
            client_ref=ref,
        )

    # ── channel_role ───────────────────────────────────────────────────

    async def _channel_role(self, args: dict[str, Any]) -> Proposal:
        ref = str(args["client_ref"])
        channel_id = str(args["channel_id"]).strip()
        role = str(args.get("role") or "").strip() or None

        channels = await self._get(f"/console/clients/{ref}/channels")
        if not isinstance(channels, list):  # pragma: no cover - el router da lista
            channels = []
        by_id = {str(c.get("id")): c for c in channels}
        target = by_id.get(channel_id)
        if target is None:
            raise ProposalRefused(
                ToolError(
                    "bad_arguments",
                    f"El cliente {ref} no tiene un canal con id {channel_id}. "
                    "Lee console.list_channels y usa el id exacto.",
                )
            )
        before = target.get("role")
        if before == role:
            raise ProposalRefused(
                ToolError(
                    "no_change",
                    f"Ese canal ya tiene el rol {role or 'sin asignar'}. Nada que cambiar.",
                )
            )

        roles = {str(c.get("id")): c.get("role") for c in channels}
        after_roles = {**roles, channel_id: role}
        unlabelled = sum(1 for v in after_roles.values() if not v)

        impact = [
            _impact("channels_affected", 1),
            _impact("channels_total", len(channels)),
        ]
        if len(channels) > 1 and unlabelled:
            # La regla de negocio real: con más de un canal activo y alguno
            # sin etiquetar, la plataforma rechaza el envío en vez de
            # adivinar. Se avisa aquí porque el cambio puede DEJAR al cliente
            # en ese estado sin que nadie lo pretendiera.
            impact.append(_impact("channels_unlabelled_after", unlabelled, "warn"))

        return Proposal(
            kind="channel_role",
            title=f"Etiquetar un canal de {ref} como {role or 'sin rol'}",
            preview={
                "client_ref": ref,
                "summary": f"{before or 'sin rol'} → {role or 'sin rol'}",
            },
            diff=[
                {"op": "del", "line": 1, "before": f"role: {before or 'null'}"},
                {"op": "add", "line": 1, "after": f"role: {role or 'null'}"},
            ],
            impact=impact,
            risk="medium" if len(channels) > 1 else "low",
            reversible=True,
            # TODOS los canales, no solo el que se toca: el impacto de
            # etiquetar uno depende de cómo estén etiquetados los demás.
            state_hash=canonical_hash({"roles": roles}),
            apply_method=APPLY_ROUTES["channel_role"][0],
            apply_path=APPLY_ROUTES["channel_role"][1].format(
                client_ref=ref, channel_id=channel_id
            ),
            apply_body={"role": role},
            expectations={"channel_role": role or "null"},
            client_ref=ref,
        )

    # ── usage_alerts ───────────────────────────────────────────────────

    async def _usage_alerts(self, args: dict[str, Any]) -> Proposal:
        current = await self._get("/console/usage/alerts")
        before_cap = current.get("cap_messages_month")
        before_recipients = sorted(str(r).lower() for r in (current.get("recipients") or []))
        before_enabled = bool(current.get("enabled"))

        cap = args.get("cap_messages_month")
        after_cap = before_cap if cap is None else (int(cap) or None)
        recipients_arg = args.get("recipients")
        after_recipients = (
            before_recipients
            if recipients_arg is None
            else sorted(r.lower() for r in split_list(str(recipients_arg)))
        )
        after_enabled = before_enabled if args.get("enabled") is None else bool(args["enabled"])

        if (
            after_cap == before_cap
            and after_recipients == before_recipients
            and after_enabled == before_enabled
        ):
            raise ProposalRefused(
                ToolError("no_change", "Los avisos de consumo ya están exactamente así.")
            )

        return Proposal(
            kind="usage_alerts",
            title="Cambiar los avisos de consumo del partner",
            preview={
                "summary": (
                    f"tope {before_cap or 'sin tope'} → {after_cap or 'sin tope'}, "
                    f"{len(after_recipients)} destinatarios, "
                    f"{'activados' if after_enabled else 'desactivados'}"
                ),
                # Enmascarados en origen: son correos de terceros y esto va
                # al log durable y al contexto del modelo.
                "recipients_masked": [mask_email(r) for r in after_recipients],
            },
            diff=[
                {"op": "del", "line": 1, "before": f"cap: {before_cap or 'null'}"},
                {"op": "add", "line": 1, "after": f"cap: {after_cap or 'null'}"},
            ],
            impact=[
                _impact("recipients", len(after_recipients)),
                _impact("alerts_enabled", str(after_enabled).lower()),
            ],
            risk="low",
            reversible=True,
            state_hash=canonical_hash(
                {
                    "cap": before_cap,
                    "recipients": before_recipients,
                    "enabled": before_enabled,
                }
            ),
            apply_method=APPLY_ROUTES["usage_alerts"][0],
            apply_path=APPLY_ROUTES["usage_alerts"][1],
            apply_body={
                "cap_messages_month": after_cap,
                "recipients": after_recipients,
                "enabled": after_enabled,
            },
            expectations={
                "alerts_cap": str(after_cap) if after_cap is not None else "null",
                "alerts_recipients": str(len(after_recipients)),
            },
        )

    # ── invite ─────────────────────────────────────────────────────────

    async def _invite(self, args: dict[str, Any]) -> Proposal:
        email = str(args["email"]).strip().lower()
        role = str(args["role"]).strip()
        if _EMAIL.match(email) is None:
            raise ProposalRefused(
                ToolError("bad_arguments", f"{email!r} no parece un correo. Pide el correo bueno.")
            )

        me = await self._get("/console/me")
        caller_role = str(me.get("role") or "")
        if ROLE_RANK.get(role, 99) > ROLE_RANK.get(caller_role, 0):
            # Garantía C6. El router también negaría la escritura por
            # permisos en la mayoría de los casos, pero no en todos (un
            # ``admin`` con ``team:manage`` puede invitar a un ``owner``), y
            # sobre todo: el "no" tiene que llegar aquí, con un motivo que el
            # modelo pueda decir en voz alta, no como un 403 opaco al aplicar.
            raise ProposalRefused(
                ToolError(
                    "role_escalation",
                    f"No puedes invitar a alguien como {role!r}: tu rol es {caller_role!r} y "
                    "nadie puede dar más permisos de los que tiene. Dilo tal cual y ofrece "
                    "invitar con un rol igual o menor.",
                )
            )

        team = await self._get("/console/team")
        members = sorted(str(m.get("email") or "").lower() for m in (team.get("members") or []))
        pending = sorted(str(i.get("email") or "").lower() for i in (team.get("invitations") or []))
        if email in members:
            raise ProposalRefused(
                ToolError("already_exists", "Esa persona ya es miembro del partner.")
            )
        if email in pending:
            raise ProposalRefused(
                ToolError("already_exists", "Esa persona ya tiene una invitación pendiente.")
            )

        return Proposal(
            kind="invite",
            title=f"Invitar a alguien como {role}",
            preview={"email_masked": mask_email(email), "role": role},
            diff=None,
            impact=[
                _impact("role", role),
                _impact("members_after", len(members) + 1),
            ],
            risk="medium",
            reversible=True,  # la invitación se revoca
            state_hash=canonical_hash(
                {"members": members, "pending": pending, "caller_role": caller_role}
            ),
            apply_method=APPLY_ROUTES["invite"][0],
            apply_path=APPLY_ROUTES["invite"][1],
            apply_body={"email": email, "role": role},
            expectations={"invitation_pending": "true"},
        )

    # ── allocation ──────────────────────────────────────────────────────

    async def _allocation(self, args: dict[str, Any]) -> Proposal:
        ref = str(args["client_ref"]).strip()
        cap = int(args["cap"])
        if cap < 0:
            raise ProposalRefused(
                ToolError(
                    "bad_arguments",
                    "El tope tiene que ser un entero ≥ 0. Manda el número nuevo, no un delta.",
                )
            )
        # C1: un ref ajeno y uno inexistente son el mismo 404 opaco.
        await self._get(f"/console/clients/{ref}")
        wallet = await self._get("/console/wallet")
        rows = await self._get("/console/wallet/allocations")
        if not isinstance(rows, list):  # pragma: no cover - el router da lista
            rows = []
        current = next((r for r in rows if str(r.get("client_ref")) == ref), None)
        before_cap = int((current or {}).get("cap") or 0)
        if current is not None and before_cap == cap:
            raise ProposalRefused(
                ToolError(
                    "no_change",
                    f"El cliente {ref} ya tiene tope {cap}. Nada que cambiar.",
                )
            )
        available = int(wallet.get("available") or 0)
        others = sum(int(r.get("cap") or 0) for r in rows if str(r.get("client_ref")) != ref)
        if others + cap > available:
            raise ProposalRefused(
                ToolError(
                    "over_allocated",
                    f"La suma de topes ({others + cap}) superaría lo disponible "
                    f"({available}). Baja otro tope o recarga tokens antes de "
                    "proponer este.",
                )
            )

        return Proposal(
            kind="allocation",
            title=f"Fijar el cupo de {ref} a {cap}",
            preview={
                "client_ref": ref,
                "summary": f"{before_cap} → {cap}",
                "before_cap": before_cap,
                "after_cap": cap,
            },
            diff=[
                {"op": "del", "line": 1, "before": f"cap: {before_cap}"},
                {"op": "add", "line": 1, "after": f"cap: {cap}"},
            ],
            impact=[
                _impact("allocation_cap", cap),
                _impact("others_caps", others),
                _impact("wallet_available", available),
            ],
            risk="medium" if cap > before_cap else "low",
            reversible=True,
            state_hash=canonical_hash(
                {
                    "client_ref": ref,
                    "cap_actual": before_cap,
                    "available": available,
                    "suma_otros_caps": others,
                }
            ),
            apply_method=APPLY_ROUTES["allocation"][0],
            apply_path=APPLY_ROUTES["allocation"][1].format(client_ref=ref),
            apply_body={"cap": cap},
            expectations={"allocation_cap": str(cap)},
            client_ref=ref,
        )

    async def _model(self, args: dict[str, Any]) -> Proposal:
        from nexus_api.core.respond_catalog import RESPOND_MODEL_ID_SET

        ref = str(args["client_ref"]).strip()
        model_id = str(args["model_id"]).strip()
        if model_id not in RESPOND_MODEL_ID_SET:
            raise ProposalRefused(
                ToolError(
                    "unknown_model",
                    "Ese model_id no está en el catálogo cerrado. Usa uno de "
                    "openai/gpt-5.6-sol, openai/gpt-5.6-terra o "
                    "openai/gpt-5.6-luna. No existe el alias gpt-5.6 aquí.",
                )
            )
        catalog = await self._get("/console/models")
        ids = {str(row.get("model_id")) for row in (catalog if isinstance(catalog, list) else [])}
        if model_id not in ids:
            raise ProposalRefused(
                ToolError(
                    "unknown_model",
                    "Ese model_id no está en el catálogo cerrado. "
                    "Lee console.list_models y elige uno de los tres.",
                )
            )
        current = await self._get(f"/console/clients/{ref}/model")
        before = str((current or {}).get("model_id") or "")
        if before == model_id:
            raise ProposalRefused(
                ToolError(
                    "no_change",
                    f"El cliente {ref} ya responde con {model_id}. Nada que cambiar.",
                )
            )

        return Proposal(
            kind="model",
            title=f"Fijar el modelo de {ref} a {model_id}",
            preview={
                "client_ref": ref,
                "summary": f"{before or '(vacío)'} → {model_id}",
                "before_model_id": before,
                "after_model_id": model_id,
            },
            diff=[
                {"op": "del", "line": 1, "before": f"model_id: {before or '(vacío)'}"},
                {"op": "add", "line": 1, "after": f"model_id: {model_id}"},
            ],
            impact=[_impact("model_id", model_id)],
            risk="medium",
            reversible=True,
            state_hash=canonical_hash({"client_ref": ref, "model_id": before}),
            apply_method=APPLY_ROUTES["model"][0],
            apply_path=APPLY_ROUTES["model"][1].format(client_ref=ref),
            apply_body={"model_id": model_id},
            expectations={"model_id": model_id},
            client_ref=ref,
        )

    # ── soporte (CO-08, §4) ────────────────────────────────────────────

    async def _knowledge(self, args: dict[str, Any]) -> Proposal:
        scope = str(args.get("scope") or "").strip()
        if scope not in {"partner", "client"}:
            raise ProposalRefused(
                ToolError(
                    "bad_arguments",
                    "scope es obligatorio y solo admite partner o client.",
                )
            )
        url = str(args.get("url") or "").strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            raise ProposalRefused(
                ToolError("bad_arguments", "Manda una URL http(s) pública para indexar.")
            )
        title = str(args.get("title") or "").strip() or None
        ref: str | None = None
        if scope == "client":
            ref = str(args.get("client_ref") or "").strip() or None
            if not ref:
                raise ProposalRefused(
                    ToolError(
                        "bad_arguments",
                        "Si el alcance es client, client_ref es obligatorio.",
                    )
                )
            listing = await self._get(f"/console/clients/{ref}/knowledge")
            apply_path = f"/console/clients/{ref}/knowledge/url"
            headline = f"Añadir al conocimiento del cliente {ref}"
        else:
            listing = await self._get("/console/knowledge")
            apply_path = APPLY_ROUTES["knowledge"][1]
            headline = "Añadir al playbook del partner"
        items = listing.get("items") if isinstance(listing, dict) else []
        if any(str((row or {}).get("source_url") or "") == url for row in (items or [])):
            raise ProposalRefused(
                ToolError("no_change", "Esa URL ya está en el alcance. Nada que añadir.")
            )
        body: dict[str, Any] = {"url": url}
        if title:
            body["title"] = title
        return Proposal(
            kind="knowledge",
            title=headline,
            preview={
                "scope": scope,
                "summary": headline,
                "url": url,
                "title": title,
                "client_ref": ref,
            },
            diff=[
                {"op": "add", "line": 1, "after": f"url: {url}"},
            ],
            impact=[_impact("knowledge_scope", scope), _impact("knowledge_url", url)],
            risk="low",
            reversible=True,
            state_hash=canonical_hash({"scope": scope, "url": url, "client_ref": ref}),
            apply_method=APPLY_ROUTES["knowledge"][0],
            apply_path=apply_path,
            apply_body=body,
            expectations={"knowledge_url": url},
            client_ref=ref,
        )

    async def _pack(self, args: dict[str, Any]) -> Proposal:
        from nexus_api.packs.schema import WorkflowPackIn, parse_workflow_body

        ref = str(args["client_ref"]).strip()
        current = await self._get(f"/console/clients/{ref}/workflow")
        steps = split_list(args.get("steps"))
        trigger = str(args.get("trigger") or "").strip()
        template_id = str(args.get("template_id") or "").strip() or None
        hour = args.get("hour")
        minute = args.get("minute")
        timezone = str(args.get("timezone") or "").strip() or None
        enabled = True if args.get("enabled") is None else bool(args["enabled"])
        payload: dict[str, Any] = {
            "client_ref": ref,
            "trigger": trigger,
            "steps": steps,
            "enabled": enabled,
            "stop": "end",
        }
        if template_id:
            payload["template_id"] = template_id
        if trigger == "cron":
            missing: list[dict[str, Any]] = []
            if hour is None:
                missing.append(
                    {
                        "key": "hour",
                        "label": "Hora local",
                        "why": "El cron se persiste en UTC; la UI usa tu zona.",
                        "examples": ["9"],
                        "required": True,
                    }
                )
            if minute is None:
                missing.append(
                    {
                        "key": "minute",
                        "label": "Minuto",
                        "why": "Sin minuto no hay hora de envío.",
                        "examples": ["0"],
                        "required": True,
                    }
                )
            if not timezone:
                missing.append(
                    {
                        "key": "timezone",
                        "label": "Zona horaria",
                        "why": "Solo para la UI; se guarda UTC.",
                        "examples": ["Europe/Madrid"],
                        "required": True,
                    }
                )
            if missing:
                raise IntakeRequired(missing)
            payload["cron"] = {
                "hour": int(hour),
                "minute": int(minute),
                "timezone": timezone,
            }
        try:
            spec = parse_workflow_body(WorkflowPackIn.model_validate(payload))
        except Exception as exc:
            raise ProposalRefused(ToolError("bad_arguments", str(exc))) from exc
        apply_body = spec.model_dump(mode="json", exclude_none=True)
        apply_body.pop("partner_id", None)
        before_steps = list((current or {}).get("steps") or [])
        after_steps = list(spec.steps)
        return Proposal(
            kind="pack",
            title=f"Aplicar pack de {ref}",
            preview={
                "client_ref": ref,
                "summary": f"{spec.trigger}: {', '.join(spec.steps)}",
                "trigger": spec.trigger,
                "steps": spec.steps,
                "template_id": spec.template_id,
            },
            diff=[
                {"op": "del", "line": 1, "before": f"steps: {before_steps}"},
                {"op": "add", "line": 1, "after": f"steps: {after_steps}"},
            ],
            impact=[
                _impact("pack_trigger", spec.trigger),
                _impact("pack_steps", ",".join(spec.steps)),
            ],
            risk="medium",
            reversible=True,
            state_hash=canonical_hash(
                {"client_ref": ref, "version": (current or {}).get("version")}
            ),
            apply_method=APPLY_ROUTES["pack"][0],
            apply_path=APPLY_ROUTES["pack"][1].format(client_ref=ref),
            apply_body=apply_body,
            expectations={"pack_steps": ",".join(spec.steps)},
            client_ref=ref,
        )

    async def _support_help(self, args: dict[str, Any]) -> Proposal:
        return await self._support("support_help", args)

    async def _support_capability(self, args: dict[str, Any]) -> Proposal:
        return await self._support("support_capability", args)

    async def _support(self, kind: str, args: dict[str, Any]) -> Proposal:
        """El ticket, calculado y no abierto.

        Lo que aquí se LEE es el documento de capacidades: es lo que impide
        pedir como funcionalidad algo que ya existe o que se decidió no
        hacer (§5.2), y es lo que hace que este ``kind`` tenga una lectura
        que verificar como cualquier otro.

        Si además hay ``client_ref``, se resuelve por el router: un ref
        ajeno y uno inexistente dan el mismo 404 opaco, así que un ticket no
        puede servir para averiguar la cartera de otro partner.
        """
        from nexus_api.companion.tools.support import (
            CapabilitiesUnavailable,
            SupportRefused,
            build_support_draft,
            load_capabilities,
            ticket_impact,
            ticket_title,
        )

        try:
            document = load_capabilities()
        except CapabilitiesUnavailable as exc:
            raise ProposalRefused(
                ToolError(
                    "unavailable",
                    "No se pudo leer el documento de capacidades, así que no sé "
                    "si esto ya existe. Dilo tal cual y no abras el ticket a "
                    "ciegas.",
                )
            ) from exc

        ref = str(args.get("client_ref") or "").strip() or None
        if ref is not None:
            # Se lee la ficha para confirmar que el cliente es de este
            # partner. Vale por sí misma: un ticket con un ref inventado
            # manda a soporte a buscar algo que no existe.
            await self._get(f"/console/clients/{ref}")

        try:
            draft = build_support_draft(
                kind,
                args,
                checked=self.checked,
                document=document,
                client_ref=ref,
            )
        except SupportRefused as refused:
            raise ProposalRefused(refused.error) from refused

        return Proposal(
            kind=kind,
            title=ticket_title(draft),
            preview=draft.as_preview(),
            # No hay diff: un ticket no cambia un estado que se pueda
            # comparar línea a línea. Inventar uno sería decorado.
            diff=None,
            impact=ticket_impact(draft),
            risk="low",
            reversible=True,
            # El hash cuelga de la VERSIÓN del documento de capacidades: si
            # alguien publica una versión nueva entre la propuesta y el sí,
            # lo que el Companion afirmó sobre qué existe puede haber dejado
            # de ser cierto, y la propuesta tiene que rehacerse.
            state_hash=canonical_hash(
                {
                    "capabilities_version": document.version,
                    "topic": draft.topic,
                    "category": draft.category,
                }
            ),
            apply_method=APPLY_ROUTES[kind][0],
            apply_path=APPLY_ROUTES[kind][1],
            apply_body=draft.as_body(),
            # No hay ticket que releer (§25.1: no se crea un sistema de
            # tickets), pero sí hay algo que prometimos y se puede
            # comprobar: que la fila aterrizó en el centro de
            # notificaciones del partner. Es la verificación honesta de lo
            # que este ``kind`` hace de verdad.
            expectations={"ticket_visible": "true"},
            client_ref=ref,
        )


# ── utilidades internas ────────────────────────────────────────────────


def _editable_version(bundle: dict[str, Any]) -> dict[str, Any] | None:
    """La versión sobre la que se edita: el borrador si lo hay, si no la
    activa. Es exactamente lo que hace la consola, y por eso el diff que se
    enseña es el mismo que la persona vería en la pantalla."""
    versions = bundle.get("versions") or []
    for v in versions:
        if v.get("status") == "staged":
            return dict(v)
    active = bundle.get("active_version")
    if active is not None:
        for v in versions:
            if int(v.get("version") or 0) == int(active):
                return dict(v)
    return dict(versions[0]) if versions else None


def _dig(obj: dict[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = obj
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _plant(obj: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    node = obj
    for key in path[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    node[path[-1]] = value


def _translate(response: httpx.Response, path: str) -> ToolError:
    detail: str | None = None
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("detail"), str):
            detail = body["detail"]
    except ValueError:
        detail = None
    return translate_status(response.status_code, detail, tool=f"la lectura de {path}")


__all__ = [
    "APPLY_ROUTES",
    "DIFF_MAX_OPS",
    "IRREVERSIBLE_KINDS",
    "POLICY_FIELDS",
    "ROLE_RANK",
    "Proposal",
    "ProposalBuilder",
    "ProposalRefused",
    "canonical_hash",
    "line_diff",
    "mask_email",
    "short_digest",
    "split_list",
]
