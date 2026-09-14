"""Spec 008 · US3 — la puerta de versión mínima.

**El caso que va primero es el que más importa**: sin mínimo declarado no se
rechaza a nadie. Es el estado del primer despliegue y el que más fácil se rompe
al añadir la puerta — y romperlo significa dejar fuera a todas las máquinas a la
vez, que es el peor resultado posible de un mecanismo que existe para avisar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.desktop_version import (
    BLOCKING_REASONS,
    MalformedVersion,
    MinimumVersion,
    is_blocked,
    parse_version,
)

AYER = datetime.now(UTC) - timedelta(days=1)
MANANA = datetime.now(UTC) + timedelta(days=1)


def vigente(version: str = "1.2.0", reason: str = "contract") -> MinimumVersion:
    return MinimumVersion(version=version, reason=reason, effective_from=AYER)


# ── R4.4: el estado del primer despliegue ───────────────────────────────


def test_sin_minimo_declarado_no_se_rechaza_a_nadie() -> None:
    assert is_blocked("0.0.1", None) is False
    assert is_blocked(None, None) is False


# ── R4.5: el preaviso, comprobable ──────────────────────────────────────


def test_un_minimo_que_aun_no_entro_en_vigor_no_cierra_la_puerta() -> None:
    """Poder declararlo con fecha futura es lo que permite avisar antes de
    rechazar. Sin esto, el preaviso sería una intención y no un mecanismo."""
    futuro = MinimumVersion(version="9.9.9", reason="contract", effective_from=MANANA)
    assert is_blocked("1.0.0", futuro) is False


def test_el_mismo_minimo_ya_en_vigor_si_cierra() -> None:
    assert is_blocked("1.0.0", vigente("9.9.9")) is True


# ── R4.6: avisar y bloquear son distintos ───────────────────────────────


def test_una_version_vieja_pero_admisible_sigue_funcionando() -> None:
    assert is_blocked("1.2.0", vigente("1.2.0")) is False
    assert is_blocked("1.3.0", vigente("1.2.0")) is False


def test_solo_la_que_cae_por_debajo_se_rechaza() -> None:
    assert is_blocked("1.1.9", vigente("1.2.0")) is True


# ── falla ABIERTO, y es deliberado ──────────────────────────────────────


def test_una_maquina_que_no_dice_su_version_pasa() -> None:
    """Las versiones viejas puede que no la manden. Dejarlas fuera por eso
    sería usar el mecanismo contra justo las instalaciones que vino a avisar."""
    assert is_blocked(None, vigente("9.9.9")) is False
    assert is_blocked("", vigente("9.9.9")) is False


def test_una_version_ilegible_pasa_en_vez_de_bloquear() -> None:
    """A diferencia de casi todo en esta plataforma, esto falla **abierto**: un
    error de formato nuestro no puede dejar a un partner sin trabajar."""
    assert is_blocked("no-es-una-version", vigente("9.9.9")) is False


def test_un_minimo_ilegible_tampoco_bloquea() -> None:
    assert is_blocked("1.0.0", vigente("tampoco-lo-es")) is False


# ── comparación ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("theirs", "minimum", "blocked"),
    [
        ("1.9.0", "1.10.0", True),  # no es orden alfabético
        ("1.10.0", "1.9.0", False),
        ("2.0", "2.0.0", False),  # distinto número de partes
        ("2.0.0", "2.0", False),
        ("1.2.0-beta.1", "1.2.0", False),  # el sufijo no se compara
        ("1.2.0+build7", "1.2.0", False),
    ],
)
def test_se_compara_por_numero_y_no_por_texto(theirs: str, minimum: str, blocked: bool) -> None:
    assert is_blocked(theirs, vigente(minimum)) is blocked


def test_parse_version_no_se_cae_a_un_defecto_silencioso() -> None:
    """Un ``(0,0,0)`` por defecto dejaría siempre fuera; un infinito, siempre
    dentro. Las dos son decisiones silenciosas, así que levanta y decide quien
    llama — y el latido decide dejar pasar."""
    for malo in ("", "   ", "abc", "1.x.3"):
        with pytest.raises(MalformedVersion):
            parse_version(malo)


# ── R4.7: para qué se puede usar ────────────────────────────────────────


def test_la_lista_de_motivos_es_cerrada() -> None:
    """Bloquear se reserva a contrato roto o seguridad. No es una palanca para
    empujar mejoras: una máquina bloqueada es un partner que no puede trabajar."""
    assert {"contract", "security"} == BLOCKING_REASONS
