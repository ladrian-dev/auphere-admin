"""Lo que se entrega a Apple y a Google — spec 031, contracts/push.md §Payload.

Funciones puras, para que lo que sale hacia fuera se pueda barrer entero
(``test_push_payload_no_customer_content``): un ``Notice`` ya compuesto entra y
sale el cuerpo exacto de APNs o de FCM, con sus cabeceras.

Los dos llevan los datos de la app donde ``expo-notifications`` los lee —en iOS,
bajo la clave ``body`` del payload; en Android, como mensaje de datos con
``title``/``message``/``channelId``/``body`` (JSON)—, así tocar el aviso abre su
pantalla con la app abierta o cerrada.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

#: Por tipo: nivel de interrupción de iOS, categoría (sin «:» ni «-», que
#: expo-notifications no admite), canal de Android y prioridad de FCM.
KIND_CONFIG: dict[str, dict[str, str]] = {
    "inbox.waiting": {
        "interruption": "time-sensitive",
        "category": "inbox_waiting",
        "channel": "waiting_v1",
        "fcm_priority": "high",
    },
    "inbox.message_for_you": {
        "interruption": "active",
        "category": "inbox_message",
        "channel": "messages_v1",
        "fcm_priority": "high",
    },
    "client.balance": {
        "interruption": "active",
        "category": "client_balance",
        "channel": "balance_v1",
        "fcm_priority": "normal",
    },
    # Spec 043: los tres de Reservas comparten el canal y la categoría que la
    # app crea (``reservations_v1``, ``reservations``).
    "reservas.agent_change": {
        "interruption": "active",
        "category": "reservations",
        "channel": "reservations_v1",
        "fcm_priority": "high",
    },
    "reservas.cancelled_today": {
        "interruption": "active",
        "category": "reservations",
        "channel": "reservations_v1",
        "fcm_priority": "high",
    },
    "reservas.waitlist_accepted": {
        "interruption": "active",
        "category": "reservations",
        "channel": "reservations_v1",
        "fcm_priority": "normal",
    },
    # Spec 047: el canal y la categoría que la app 1.2.0 crea.
    "agents.state": {
        "interruption": "active",
        "category": "agents",
        "channel": "agents_v1",
        "fcm_priority": "high",
    },
}

#: Un aviso que no llega en una hora ya no sirve: espera a una persona *ahora*.
TTL_SECONDS = 3600

APP_SCHEME = "auphere-customers"


@dataclass(frozen=True)
class Notice:
    """Un aviso listo para salir. ``thread`` agrupa y reemplaza los de una
    misma conversación (``conversation_id``) o los de saldo."""

    kind: str
    title: str
    body: str
    url: str
    thread: str
    badge: int


def inbox_url(conversation_id: object) -> str:
    return f"{APP_SCHEME}://inbox/{conversation_id}"


def usage_url() -> str:
    return f"{APP_SCHEME}://usage"


def agents_url(agent_id: object, channel_id: object | None = None) -> str:
    """Spec 047: el agente (y, si lo hay, su número) en la app."""
    base = f"{APP_SCHEME}://agents/{agent_id}"
    return f"{base}/channels/{channel_id}" if channel_id else base


def reservas_url(booking_id: object) -> str:
    """Spec 043: la reserva en la app."""
    return f"{APP_SCHEME}://reservas/{booking_id}"


def apns(
    notice: Notice, *, topic: str, now: float | None = None
) -> tuple[dict[str, str], dict[str, Any]]:
    """Cabeceras y cuerpo de APNs (HTTP/2, ``/3/device/<token>``)."""
    cfg = KIND_CONFIG[notice.kind]
    headers = {
        "apns-push-type": "alert",
        "apns-priority": "10",
        "apns-topic": topic,
        "apns-collapse-id": notice.thread[:64],
        "apns-expiration": str(int((now or time.time()) + TTL_SECONDS)),
    }
    body: dict[str, Any] = {
        "aps": {
            "alert": {"title": notice.title, "body": notice.body},
            "sound": "default",
            "badge": notice.badge,
            "interruption-level": cfg["interruption"],
            "category": cfg["category"],
            "thread-id": notice.thread,
        },
        # expo-notifications lee aquí los datos de un aviso remoto en iOS.
        "body": {"url": notice.url, "kind": notice.kind},
    }
    return headers, body


def fcm(notice: Notice, *, token: str) -> dict[str, Any]:
    """El mensaje de FCM HTTP v1. Solo datos: lo pinta expo-notifications con el
    canal del tipo, que la app creó con visibilidad privada (R8.10)."""
    cfg = KIND_CONFIG[notice.kind]
    return {
        "message": {
            "token": token,
            "android": {
                "priority": cfg["fcm_priority"],
                "ttl": f"{TTL_SECONDS}s",
                "collapse_key": notice.thread[:64],
            },
            "data": {
                "title": notice.title,
                "message": notice.body,
                "channelId": cfg["channel"],
                "categoryId": cfg["category"],
                "threadIdentifier": notice.thread,
                "badge": str(notice.badge),
                "body": json.dumps({"url": notice.url, "kind": notice.kind}),
            },
        }
    }


__all__ = [
    "KIND_CONFIG",
    "TTL_SECONDS",
    "Notice",
    "agents_url",
    "apns",
    "fcm",
    "inbox_url",
    "usage_url",
]
