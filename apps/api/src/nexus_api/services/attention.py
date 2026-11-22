"""La regla única de atención — spec 047, T011 (requisitos 7.2 y 7.3).

Decide si un cliente «necesita atención» y por qué. Es **una** regla y vive
aquí: la lista de clientes, el Panel del partner («Necesita tu atención») y ⌘K
la leen de la API; ninguna la recalcula.

Los motivos, de más a menos grave (7.2), con el arreglo que el Panel pone en
cada fila (48.2):

1. ``no_balance`` — la bolsa está vacía → «Asignar saldo» / «Pedir saldo»;
2. ``channel_problem`` — un canal con problemas, o desconectado sin que nadie
   lo pidiera → «Arreglar»;
3. ``integration_reauth`` — una integración que hay que volver a autorizar →
   «Reconectar»;
4. ``agent_cap`` — un agente en pausa por su tope → «Subir el tope»;
5. ``agent_without_channel`` — un agente «Listo · sin canal» o «En prueba» →
   «Conectar canal»;
6. ``low_balance`` — por debajo del 20 % de la bolsa o para menos de 7 días →
   «Asignar saldo»;
7. ``no_agents`` — ningún agente sin archivar → «Nuevo agente».

El estado de cada agente y de cada canal sale de ``agent_lifecycle`` (un solo
cálculo, 25.5): un canal en pausa no es un problema, y uno «A todos» que se ha
caído sí lo es.

Una decisión que la spec no escribe: **un cliente archivado no necesita
atención**. Archivar es apartarlo a propósito —sus agentes quedan en pausa y su
bolsa no corre— y sale en «Archivados», no en «Necesitan atención».

La regla no ve importes: compara bolsas de monedas distintas por los días que
les quedan y por su porcentaje (7.5). Funciones puras, sin base ni reloj.

**Spec 071: la lista entera.** A lo de cada cliente se suma lo del partner
(``PARTNER_REASONS``): el tope de «Construcción y pruebas» al 80 % o agotado, la
cuenta baja o vacía y un cobro fallido. Cada fila lleva su alcance, su gravedad
(``severity_of``), su arreglo y lo justo para el texto (``data``), y la lista va de
peor a mejor (``order_items``; ``contracts/api.md``). Lo que la lee de la base es
``attention_live``: el Panel, ``GET /console/attention`` y la resolución de los
avisos (``CONDITION_CODES``) leen todos de allí.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

from nexus_api.services.agent_lifecycle import (
    AgentFacts,
    agent_visible_state,
    channel_visible_state,
)

#: Los motivos, de más a menos grave.
ATTENTION_REASONS: tuple[str, ...] = (
    "no_balance",
    "channel_problem",
    "integration_reauth",
    "agent_cap",
    "agent_without_channel",
    "low_balance",
    "no_agents",
)
#: «Saldo bajo»: por debajo de este porcentaje de la bolsa…
LOW_BALANCE_PCT = 20
#: …o para menos de estos días al ritmo de los últimos 7.
LOW_BALANCE_DAYS = 7


@dataclass(frozen=True)
class ClientFacts:
    """Lo que la regla necesita de un cliente.

    ``pct_left`` es lo que queda de la bolsa sobre su base (de 0 a 100) y
    ``days_left``, los días al ritmo de los últimos 7 días completos; ``None``
    cuando no hay datos para estimarlo (``contracts/events.md`` §1.4).
    ``ref`` identifica al cliente y desempata el orden de la lista.
    """

    ref: str
    archived: bool = False
    bag_empty: bool = False
    pct_left: float | None = None
    days_left: float | None = None
    reauth_integrations: int = 0
    agents: tuple[AgentFacts, ...] = ()


@dataclass(frozen=True)
class AttentionReason:
    """Un motivo y cuántas cosas lo causan («2 canales con problemas»)."""

    code: str
    count: int = 1


@dataclass(frozen=True)
class Attention:
    """Los motivos de un cliente, de más a menos grave."""

    reasons: tuple[AttentionReason, ...] = ()

    @property
    def needs_attention(self) -> bool:
        return bool(self.reasons)

    @property
    def top(self) -> AttentionReason | None:
        return self.reasons[0] if self.reasons else None


def _low_balance(client: ClientFacts) -> bool:
    if client.pct_left is not None and client.pct_left < LOW_BALANCE_PCT:
        return True
    return client.days_left is not None and client.days_left < LOW_BALANCE_DAYS


def attention(client: ClientFacts) -> Attention:
    """Los motivos del requisito 7.2 que se cumplen, en su orden."""
    if client.archived:
        return Attention()

    channel_problems = 0
    capped = 0
    without_channel = 0
    live_agents = 0
    for agent in client.agents:
        for channel in agent.channels:
            state = channel_visible_state(channel)
            if state.code == "problem" or (
                state.code == "disconnected" and not channel.disconnected_on_request
            ):
                channel_problems += 1
        visible = agent_visible_state(agent)
        if visible.code == "archived":
            continue
        live_agents += 1
        if visible.code == "paused" and visible.reason == "agent_cap":
            capped += 1
        elif visible.code in ("ready_no_channel", "testing"):
            without_channel += 1

    found: dict[str, int] = {}
    if client.bag_empty:
        found["no_balance"] = 1
    if channel_problems:
        found["channel_problem"] = channel_problems
    if client.reauth_integrations > 0:
        found["integration_reauth"] = client.reauth_integrations
    if capped:
        found["agent_cap"] = capped
    if without_channel:
        found["agent_without_channel"] = without_channel
    # Una bolsa vacía también está por debajo del 20 %: se dice una vez, la peor.
    if not client.bag_empty and _low_balance(client):
        found["low_balance"] = 1
    if live_agents == 0:
        found["no_agents"] = 1
    return Attention(
        tuple(AttentionReason(code, found[code]) for code in ATTENTION_REASONS if code in found)
    )


def _days_key(client: ClientFacts) -> float:
    # Una bolsa vacía no tiene días por delante aunque no haya ritmo con que
    # estimarlos; sin datos, al final de su grupo.
    if client.bag_empty:
        return 0.0
    return math.inf if client.days_left is None else client.days_left


def _pct_key(client: ClientFacts) -> float:
    if client.bag_empty:
        return 0.0
    return math.inf if client.pct_left is None else client.pct_left


def list_order(clients: Iterable[ClientFacts]) -> list[ClientFacts]:
    """7.3: primero los que necesitan atención y, dentro de cada grupo, de
    menos a más días de saldo; a igualdad de días, el porcentaje y la
    referencia, para que el orden sea estable."""
    return sorted(
        clients,
        key=lambda c: (
            not attention(c).needs_attention,
            _days_key(c),
            _pct_key(c),
            c.ref,
        ),
    )


# ── spec 071: lo del partner ───────────────────────────────────────────────────

#: Los motivos del partner, de más a menos grave dentro de su gravedad.
PARTNER_REASONS: tuple[str, ...] = (
    "build_cap_exhausted",
    "build_cap_warning",
    "account_empty",
    "account_low",
    "billing_payment_failed",
)
#: Lo que para algo o ya se ha parado (``contracts/api.md``); el resto, ``warning``.
CRITICAL_CODES: Final = frozenset(
    {
        "build_cap_exhausted",
        "account_empty",
        "billing_payment_failed",
        "no_balance",
        "channel_problem",
    }
)
#: Los umbrales con que avisa ``wallet_alerts`` del saldo de la cuenta (% gastado).
#: La regla nunca dice menos que el aviso (research.md §R3): si no, soltar la clave
#: del aviso lo haría volver en cada pasada del emisor.
ACCOUNT_LOW_NOTICE_PCT: Final = 80
ACCOUNT_EMPTY_NOTICE_PCT: Final = 100


def severity_of(code: str) -> str:
    return "critical" if code in CRITICAL_CODES else "warning"


@dataclass(frozen=True)
class BuildFacts:
    """La partida del mes, con el estado que le da ``build_budget`` (el que frena)."""

    cap_micros: int
    spent_micros: int
    state: str  # ok · warning · exhausted
    currency: str


@dataclass(frozen=True)
class AccountFacts:
    """La cuenta, en su moneda. ``available_micros`` es lo asignable (la cifra de
    «Saldo disponible»); ``pct_left``, lo que queda de lo cargado en el mes;
    ``days_left``, los días al ritmo de los últimos 7 (``None``: sin datos);
    ``notice_pct_used``, el porcentaje con que avisa ``wallet_alerts``."""

    available_micros: int
    currency: str
    pct_left: float | None = None
    days_left: int | None = None
    notice_pct_used: float | None = None


@dataclass(frozen=True)
class PartnerFacts:
    """Lo que la regla necesita del partner. ``None``: no se sabe (no se leyó o no
    aplica), y lo que no se sabe no se dice."""

    build: BuildFacts | None = None
    account: AccountFacts | None = None
    billing_failed: bool = False


def _account_state(account: AccountFacts) -> str | None:
    notice = account.notice_pct_used
    if account.available_micros <= 0 or (notice is not None and notice >= ACCOUNT_EMPTY_NOTICE_PCT):
        return "empty"
    if notice is not None and notice >= ACCOUNT_LOW_NOTICE_PCT:
        return "low"
    # D2: como las bolsas.
    if account.pct_left is not None and account.pct_left < LOW_BALANCE_PCT:
        return "low"
    if account.days_left is not None and account.days_left < LOW_BALANCE_DAYS:
        return "low"
    return None


def partner_attention(facts: PartnerFacts) -> tuple[AttentionReason, ...]:
    """Los motivos del partner que se cumplen, en el orden de ``PARTNER_REASONS``.
    De cada cosa se dice una vez, la peor."""
    found: set[str] = set()
    if facts.build is not None:
        if facts.build.state == "exhausted":
            found.add("build_cap_exhausted")
        elif facts.build.state == "warning":
            found.add("build_cap_warning")
    if facts.account is not None:
        state = _account_state(facts.account)
        if state is not None:
            found.add(f"account_{state}")
    if facts.billing_failed:
        found.add("billing_payment_failed")
    return tuple(AttentionReason(code) for code in PARTNER_REASONS if code in found)


# ── las filas ──────────────────────────────────────────────────────────────────

#: El arreglo de cada motivo de un cliente: la acción que se pinta y adónde lleva.
#: ``{ref}`` es la referencia del cliente.
FIXES: Final[dict[str, tuple[str, str]]] = {
    "no_balance": ("assign_balance", "/clients/{ref}?assign=1"),
    "low_balance": ("assign_balance", "/clients/{ref}?assign=1"),
    "channel_problem": ("fix_channel", "/clients/{ref}/channels"),
    "integration_reauth": ("reconnect", "/clients/{ref}/integrations"),
    "agent_cap": ("raise_cap", "/clients/{ref}/agents"),
    "agent_without_channel": ("connect_channel", "/clients/{ref}/channels"),
    "no_agents": ("new_agent", "/clients/{ref}/agents/new"),
}
#: Quien no puede asignar pide (45.7).
REQUEST_INSTEAD: Final = frozenset({"no_balance", "low_balance"})
#: El arreglo de cada motivo del partner. «Pedir ampliación» es la petición que ya
#: existe (``POST /console/usage/build-budget/extension-request``).
PARTNER_FIXES: Final[dict[str, tuple[str, str]]] = {
    "build_cap_exhausted": ("request_build_extension", "/usage"),
    "build_cap_warning": ("request_build_extension", "/usage"),
    "account_empty": ("buy_balance", "/billing"),
    "account_low": ("buy_balance", "/billing"),
    "billing_payment_failed": ("fix_billing", "/billing"),
}


@dataclass(frozen=True)
class AttentionItem:
    """Una fila de la lista (``contracts/api.md``, ``AttentionItem``)."""

    scope: str  # partner · client
    severity: str  # critical · warning
    code: str
    ref: str | None
    name: str | None
    count: int
    action: str
    href: str
    data: Mapping[str, Any] = field(default_factory=dict)


def buy_first_when_empty(items: list[AttentionItem], *, can_buy: bool) -> list[AttentionItem]:
    """Con la cuenta a 0 no hay saldo que asignar (owner, 2026-11-22): para quien
    puede comprar, las filas de saldo de sus clientes que se arreglaban asignando
    pasan a «Comprar saldo», a Facturación. Quien pide saldo lo sigue pidiendo."""
    if not can_buy or not any(i.code == "account_empty" for i in items):
        return items
    return [
        replace(i, action="buy_balance", href="/billing")
        if i.scope == "client" and i.action == "assign_balance"
        else i
        for i in items
    ]


def money(amount: int, currency: str) -> dict[str, Any]:
    return {"amount_micros": int(amount), "currency": currency}


def _partner_data(code: str, facts: PartnerFacts) -> dict[str, Any]:
    if code.startswith("build_cap") and facts.build is not None:
        b = facts.build
        pct = b.spent_micros * 100 // b.cap_micros if b.cap_micros > 0 else 100
        return {
            "pct": int(pct),
            "spent": money(b.spent_micros, b.currency),
            "cap": money(b.cap_micros, b.currency),
        }
    if code.startswith("account") and facts.account is not None:
        a = facts.account
        out: dict[str, Any] = {"available": money(max(0, a.available_micros), a.currency)}
        if code == "account_low":
            out["days_left"] = a.days_left
        return out
    return {}


def partner_items(facts: PartnerFacts) -> list[AttentionItem]:
    """Las filas del partner, cada una con su arreglo y sus cifras."""
    out: list[AttentionItem] = []
    for reason in partner_attention(facts):
        action, href = PARTNER_FIXES[reason.code]
        out.append(
            AttentionItem(
                scope="partner",
                severity=severity_of(reason.code),
                code=reason.code,
                ref=None,
                name=None,
                count=reason.count,
                action=action,
                href=href,
                data=_partner_data(reason.code, facts),
            )
        )
    return out


@dataclass(frozen=True)
class BagFigures:
    """Lo que la fila de saldo de un cliente dice de su bolsa: lo que queda, en su
    moneda (``None``: sin bolsa aún), y los días al ritmo de los últimos 7."""

    balance_micros: int | None
    currency: str
    days_left: float | None


def client_items(
    ref: str,
    name: str | None,
    found: Attention,
    *,
    can_assign: bool,
    bag: BagFigures | None = None,
) -> list[AttentionItem]:
    """Las filas de un cliente: sus motivos con el arreglo para quien mira."""
    out: list[AttentionItem] = []
    for reason in found.reasons:
        action, href = FIXES[reason.code]
        if reason.code in REQUEST_INSTEAD and not can_assign:
            action = "request_balance"
        data: dict[str, Any] = {}
        if reason.code in REQUEST_INSTEAD and bag is not None:
            if bag.balance_micros is not None:
                data["available"] = money(max(0, bag.balance_micros), bag.currency)
            if reason.code == "low_balance":
                data["days_left"] = None if bag.days_left is None else int(bag.days_left)
        out.append(
            AttentionItem(
                scope="client",
                severity=severity_of(reason.code),
                code=reason.code,
                ref=ref,
                name=name,
                count=reason.count,
                action=action,
                href=href.format(ref=ref),
                data=data,
            )
        )
    return out


def _rank(item: AttentionItem) -> tuple[int, int, int, str]:
    if item.scope == "partner":
        return (item.severity != "critical", 0, PARTNER_REASONS.index(item.code), "")
    return (
        item.severity != "critical",
        1,
        ATTENTION_REASONS.index(item.code),
        item.ref or "",
    )


def order_items(items: Iterable[AttentionItem]) -> list[AttentionItem]:
    """De peor a mejor; dentro de cada gravedad, primero lo del partner y luego los
    clientes por ``ATTENTION_REASONS`` y por ``ref`` (``contracts/api.md``)."""
    return sorted(items, key=_rank)


# ── los avisos de condición (spec 071, §2.1) ───────────────────────────────────

#: Cada aviso guardado que dice una condición, con su código de la regla. Cuando su
#: código deja de estar en la lista, el aviso se resuelve solo (``attention_live``).
#: Los demás son informativos: se leen.
CONDITION_CODES: Final[dict[str, str]] = {
    "client.wallet.low": "low_balance",
    "client.wallet.empty": "no_balance",
    "build.budget.warning": "build_cap_warning",
    "build.budget.exhausted": "build_cap_exhausted",
    "wallet.low": "account_low",
    "wallet.empty": "account_empty",
    "agent.cap.reached": "agent_cap",
    "channel.problem": "channel_problem",
    "integration.reauth_required": "integration_reauth",
    "billing.payment_failed": "billing_payment_failed",
}
#: Los que son del partner: se resuelven por su tipo, lleven o no un cliente (los
#: ``build.budget.*`` de antes de la 071 se colgaban de uno cualquiera).
PARTNER_CONDITION_KINDS: Final = frozenset(
    kind for kind, code in CONDITION_CODES.items() if code in PARTNER_REASONS
)
#: Un «queda poco» sigue siendo cierto cuando se ha agotado: no se resuelve mientras
#: su hermano peor siga en la lista (research.md §R4).
COVERED_BY: Final[dict[str, str]] = {
    "account_low": "account_empty",
    "low_balance": "no_balance",
    "build_cap_warning": "build_cap_exhausted",
}


def is_condition(kind: str) -> bool:
    return kind in CONDITION_CODES


def still_listed(code: str, listed: set[str]) -> bool:
    """¿Sigue el código en la lista (él o el hermano que lo cubre)?"""
    return code in listed or COVERED_BY.get(code) in listed


__all__ = [
    "ACCOUNT_EMPTY_NOTICE_PCT",
    "ACCOUNT_LOW_NOTICE_PCT",
    "ATTENTION_REASONS",
    "CONDITION_CODES",
    "COVERED_BY",
    "CRITICAL_CODES",
    "FIXES",
    "LOW_BALANCE_DAYS",
    "LOW_BALANCE_PCT",
    "PARTNER_CONDITION_KINDS",
    "PARTNER_FIXES",
    "PARTNER_REASONS",
    "REQUEST_INSTEAD",
    "AccountFacts",
    "Attention",
    "AttentionItem",
    "AttentionReason",
    "BagFigures",
    "BuildFacts",
    "ClientFacts",
    "PartnerFacts",
    "attention",
    "client_items",
    "is_condition",
    "list_order",
    "money",
    "order_items",
    "partner_attention",
    "partner_items",
    "severity_of",
    "still_listed",
]
