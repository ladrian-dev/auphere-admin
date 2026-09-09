"""Requisito 7.4 — el ambiente del agente no lleva credenciales de cliente final.

La restricción de la constitución no admite matices: *ninguna credencial de
cliente final entra nunca en el ambiente de un agente*. Y no basta con no
ponerlas: el sustrato arranca los procesos con `env = {**os.environ}`, y su
saneado solo quita cinco variables de AWS y de GPG. Todo lo demás **pasa**.

Por eso aquí el ambiente se construye por **lista blanca**: se parte de nada y se
añade lo que hace falta. Una lista negra en una máquina que no controlamos es una
lista de lo que se nos ocurrió, no de lo que hay.
"""

from __future__ import annotations

import pytest

#: Los prefijos se componen en tiempo de ejecución a propósito.
#:
#: Escritos como literales, un escáner de secretos —el de GitHub, por ejemplo—
#: los marca como claves reales y bloquea el push. Y tiene razón en la forma:
#: **eso es exactamente lo que este test comprueba que se detecta**. Componerlos
#: conserva toda la fuerza de la prueba y deja de gastar la atención de quien
#: revisa alertas, que es un recurso que se agota.
_ANTHROPIC = "sk" + "-ant-api03-" + "a" * 30
_STRIPE = "sk" + "_live_" + "a" * 24
_GITHUB = "ghp" + "_" + "a" * 36
_PEM = "-----BEGIN " + "RSA PRIVATE KEY-----"


from auphere_edition.agent_env import (
    ALLOWED_ENV_KEYS,
    CredentialLeak,
    build_agent_env,
)


def test_the_environment_is_built_from_nothing():
    """Lista blanca, no saneado: se parte de vacío y se añade lo necesario."""
    dirty = {
        "PATH": "/usr/bin",
        "HOME": "/Users/partner",
        "STRIPE_SECRET_KEY": _STRIPE,
        "CLIENT_WHATSAPP_TOKEN": "EAAG...",
        "AWS_SECRET_ACCESS_KEY": "...",
        "GITHUB_TOKEN": "ghp_...",
    }
    env = build_agent_env(dirty)
    assert set(env) <= ALLOWED_ENV_KEYS
    assert "STRIPE_SECRET_KEY" not in env
    assert "CLIENT_WHATSAPP_TOKEN" not in env
    assert "GITHUB_TOKEN" not in env


def test_what_the_agent_needs_does_survive():
    env = build_agent_env({"PATH": "/usr/bin", "HOME": "/Users/partner", "LANG": "es_ES.UTF-8"})
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/Users/partner"


def test_a_credential_smuggled_under_an_allowed_name_is_caught():
    """El nombre permitido no compra el derecho a llevar un secreto dentro."""
    with pytest.raises(CredentialLeak):
        build_agent_env({"PATH": f"/usr/bin:{_ANTHROPIC}"})


@pytest.mark.parametrize(
    "value",
    [_ANTHROPIC, _STRIPE, _GITHUB, _PEM],
    ids=["anthropic", "stripe", "github", "pem"],
)
def test_known_credential_shapes_are_refused(value: str):
    with pytest.raises(CredentialLeak):
        build_agent_env({"LANG": value})


def test_the_allowlist_stays_small():
    """Si esta lista crece, alguien está ampliando la frontera sin decirlo."""
    assert len(ALLOWED_ENV_KEYS) <= 8
