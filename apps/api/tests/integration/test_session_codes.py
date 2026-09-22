"""Spec 009 · Historia 2 — el código que trae una sesión de Google a la app.

**Lo que este fichero vigila no es que el código funcione: es que no sirva para
entrar como otro.** El de emparejamiento ata una MÁQUINA; éste ata una PERSONA,
y una llave de persona mal hecha es una puerta trasera.

Por qué NO está en ``tests/isolation/``: allí viven las 7 garantías de
``architecture/agent-isolation.md``, que son **entre tenants**. Esto no cruza
ninguna — no hay ``tenant_id``, ni RLS, ni herramientas. Es no suplantación, que
es otra cosa, y esconderla allí la mezclaría con algo distinto.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.one_time_codes import CODE_LENGTH, normalize_code
from nexus_api.db.base import get_sessionmaker
from nexus_api.services.session_codes import (
    SessionCodeRejected,
    issue_session_code,
    redeem_session_code,
)

#: Un par PKCE de juguete. El `verifier` es lo que la aplicación guarda y no
#: enseña; el `challenge` es lo que viaja al pedir el código.
VERIFIER = "un-verifier-de-prueba-suficientemente-largo-0123456789"
CHALLENGE = hashlib.sha256(VERIFIER.encode()).hexdigest()
OTRO_VERIFIER = "otro-verifier-distinto-9876543210abcdefghijklmnop"

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _principal(session, email: str | None = None) -> uuid.UUID:
    pid = uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO console_auth.principals (id, email, password_hash) "
            "VALUES (:i, :e, 'scrypt$x')"
        ),
        {"i": str(pid), "e": email or f"sc-{pid.hex[:10]}@auphere.test"},
    )
    return pid


async def _codigos_vivos(session, principal_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            sa.text(
                "SELECT count(*) FROM console_auth.session_codes "
                "WHERE principal_id = :p AND consumed_at IS NULL"
            ),
            {"p": str(principal_id)},
        )
        or 0
    )


class TestEmision:
    """Requisito 3."""

    async def test_emite_un_codigo_de_la_forma_del_emparejamiento(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            # Mismo alfabeto y misma longitud: se teclean en la misma hoja.
            assert normalize_code(code) == code
            assert len(code) == CODE_LENGTH

    async def test_guarda_el_hash_y_nunca_el_codigo(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            filas = (
                await s.execute(sa.text("SELECT code_hash FROM console_auth.session_codes"))
            ).all()
            guardado = " ".join(str(c) for fila in filas for c in fila)
            assert code not in guardado

    async def test_emitir_otro_invalida_el_anterior(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            primero = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            assert await _codigos_vivos(s, pid) == 1
            with pytest.raises(SessionCodeRejected):
                await redeem_session_code(s, code=primero, code_verifier=VERIFIER)


class TestCanje:
    """Requisito 4."""

    async def test_acuna_una_sesion_nueva_e_independiente(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            # Una sesión de navegador que ya existe.
            await s.execute(
                sa.text(
                    "INSERT INTO console_auth.principal_sessions "
                    "(token_hash, principal_id, expires_at, last_used_at, user_agent) "
                    "VALUES (:h, :p, now() + interval '7 days', now(), 'Mozilla/5.0')"
                ),
                {"h": uuid.uuid4().hex * 2, "p": str(pid)},
            )
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            token, _expires = await redeem_session_code(
                s, code=code, code_verifier=VERIFIER, user_agent="AuphereDesktop/0.1.3"
            )
            assert token

            # Dos sesiones, no una: la del navegador sigue viva.
            sesiones = (
                (
                    await s.execute(
                        sa.text(
                            "SELECT user_agent FROM console_auth.principal_sessions "
                            "WHERE principal_id = :p ORDER BY created_at"
                        ),
                        {"p": str(pid)},
                    )
                )
                .scalars()
                .all()
            )
            assert len(sesiones) == 2
            # Y se distinguen, que es lo que deja auditar qué máquina hizo qué.
            assert any("AuphereDesktop" in (ua or "") for ua in sesiones)
            assert any("Mozilla" in (ua or "") for ua in sesiones)

    async def test_cerrar_la_de_la_app_no_cierra_la_del_navegador(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            await s.execute(
                sa.text(
                    "INSERT INTO console_auth.principal_sessions "
                    "(token_hash, principal_id, expires_at, last_used_at, user_agent) "
                    "VALUES (:h, :p, now() + interval '7 days', now(), 'Mozilla/5.0')"
                ),
                {"h": uuid.uuid4().hex * 2, "p": str(pid)},
            )
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            await redeem_session_code(
                s, code=code, code_verifier=VERIFIER, user_agent="AuphereDesktop/0.1.3"
            )
            await s.execute(
                sa.text(
                    "DELETE FROM console_auth.principal_sessions "
                    "WHERE principal_id = :p AND user_agent LIKE 'AuphereDesktop%'"
                ),
                {"p": str(pid)},
            )
            quedan = (
                (
                    await s.execute(
                        sa.text(
                            "SELECT user_agent FROM console_auth.principal_sessions "
                            "WHERE principal_id = :p"
                        ),
                        {"p": str(pid)},
                    )
                )
                .scalars()
                .all()
            )
            assert quedan == ["Mozilla/5.0"]

    async def test_un_solo_uso(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            await redeem_session_code(s, code=code, code_verifier=VERIFIER)
            with pytest.raises(SessionCodeRejected):
                await redeem_session_code(s, code=code, code_verifier=VERIFIER)

    async def test_caducado_usado_e_inexistente_son_indistinguibles(self) -> None:
        """R4.5 — quien prueba códigos no puede aprender cuáles existieron."""
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)

            usado = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            await redeem_session_code(s, code=usado, code_verifier=VERIFIER)

            caducado = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            await s.execute(
                sa.text(
                    "UPDATE console_auth.session_codes SET expires_at = now() - interval '1 minute' "
                    "WHERE consumed_at IS NULL AND principal_id = :p"
                ),
                {"p": str(pid)},
            )

            motivos = set()
            for code in (usado, caducado, "ZZZZ9999"):
                with pytest.raises(SessionCodeRejected) as exc:
                    await redeem_session_code(s, code=code, code_verifier=VERIFIER)
                motivos.add(str(exc.value))
            # UNA sola frase para los tres. Si son dos, el sistema está contando.
            assert len(motivos) == 1, motivos


class TestNoSuplantacion:
    """Requisito 5 — lo que el código NO puede hacer."""

    async def test_el_codigo_no_vale_sin_el_verifier(self) -> None:
        """PKCE (RFC 7636) — **recupera la atadura que la primera enmienda perdió.**

        El `code_verifier` se genera en la aplicación y no sale de su proceso.
        Quien vea el código en la URL del retorno —en un historial, en un log de
        proxy, mirando la pantalla— no puede canjearlo: le falta el secreto.

        Esto es lo que Q2 quería y el `hostname` no podía dar.
        """
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            with pytest.raises(SessionCodeRejected) as malo:
                await redeem_session_code(s, code=code, code_verifier=OTRO_VERIFIER)
            # Y el rechazo es el mismo que el de un código inventado: si se
            # distinguieran, fallar el verifier confirmaría que el código existe.
            with pytest.raises(SessionCodeRejected) as inventado:
                await redeem_session_code(s, code="ZZZZ9999", code_verifier=VERIFIER)
            assert str(malo.value) == str(inventado.value)

    async def test_un_verifier_correcto_si_entra(self) -> None:
        """**Fija la pérdida de la enmienda del 2026-09-15, no una virtud.**

        El camino feliz, y queda registrado desde dónde (R5.3)."""
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            token, _ = await redeem_session_code(
                s,
                code=code,
                code_verifier=VERIFIER,
                ip="203.0.113.7",
                user_agent="AuphereDesktop/0.1.3",
            )
            assert token
            registrado = (
                await s.execute(
                    sa.text(
                        "SELECT ip, user_agent FROM console_auth.principal_sessions "
                        "WHERE principal_id = :p"
                    ),
                    {"p": str(pid)},
                )
            ).one()
            assert str(registrado.ip) == "203.0.113.7"
            assert "AuphereDesktop" in registrado.user_agent

    async def test_la_sesion_es_de_quien_pidio_el_codigo_y_de_nadie_mas(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            mia = await _principal(s)
            ajena = await _principal(s)
            code = await issue_session_code(s, principal_id=mia, code_challenge=CHALLENGE)
            await redeem_session_code(s, code=code, code_verifier=VERIFIER)
            de_la_ajena = int(
                await s.scalar(
                    sa.text(
                        "SELECT count(*) FROM console_auth.principal_sessions WHERE principal_id = :p"
                    ),
                    {"p": str(ajena)},
                )
                or 0
            )
            assert de_la_ajena == 0

    async def test_el_codigo_sobrevive_como_rastro_pero_no_como_secreto(self) -> None:
        """R5.5: la auditoría puede decir que se usó, sin poder reusarlo."""
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            await redeem_session_code(s, code=code, code_verifier=VERIFIER)
            fila = (
                await s.execute(
                    sa.text(
                        "SELECT principal_id, consumed_at IS NOT NULL AS usado "
                        "FROM console_auth.session_codes WHERE principal_id = :p"
                    ),
                    {"p": str(pid)},
                )
            ).one()
            assert fila.usado is True
            assert str(fila.principal_id) == str(pid)

    async def test_un_codigo_mal_formado_se_rechaza_igual(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            with pytest.raises(SessionCodeRejected):
                await redeem_session_code(s, code="no-es-un-codigo", code_verifier=VERIFIER)


class TestLimiteDeIntentos:
    """Requisito 4.6 — **el test que faltaba y que `/cso` cazó como 🔴.**

    Dos tareas citaban 4.6, las dos estaban marcadas como hechas, y no había ni
    implementación ni test: los once tests pasaban sin tocar el asunto. Queda
    aquí como recordatorio de que citar un requisito no es cubrirlo.

    Se usa un espía y no Redis de verdad **a propósito**: lo que hay que probar
    no es que Redis cuente —eso ya se prueba en `device_pairing`— sino que el
    canje **llame** al limitador en todos sus caminos de rechazo. El agujero que
    esto vigila es que alguien añada un `raise` nuevo y se olvide de castigar.
    """

    class Espia:
        def __init__(self) -> None:
            self.comprobados: list[str] = []
            self.fallos: list[str] = []
            self.limpiezas: list[str] = []

        async def check(self, key: str) -> None:
            self.comprobados.append(key)

        async def record_failure(self, key: str) -> None:
            self.fallos.append(key)

        async def clear(self, key: str) -> None:
            self.limpiezas.append(key)

    async def test_todos_los_caminos_de_rechazo_cuentan_como_fallo(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            bueno = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)

            casos = [
                ("mal formado", "no-es-un-codigo", VERIFIER),
                ("inexistente", "ZZZZ9999", VERIFIER),
                ("verifier ajeno", bueno, OTRO_VERIFIER),
            ]
            for nombre, code, verifier in casos:
                espia = self.Espia()
                with pytest.raises(SessionCodeRejected):
                    await redeem_session_code(
                        s,
                        code=code,
                        code_verifier=verifier,
                        limiter=espia,  # type: ignore[arg-type]
                        attempt_key="k",
                    )
                assert espia.comprobados == ["k"], nombre
                assert espia.fallos == ["k"], f"{nombre} no contó como fallo"

    async def test_un_canje_correcto_limpia_la_cuenta(self) -> None:
        async with get_sessionmaker()() as s, s.begin():
            pid = await _principal(s)
            code = await issue_session_code(s, principal_id=pid, code_challenge=CHALLENGE)
            espia = self.Espia()
            await redeem_session_code(
                s,
                code=code,
                code_verifier=VERIFIER,
                limiter=espia,  # type: ignore[arg-type]
                attempt_key="k",
            )
            assert espia.fallos == []
            # Quien acierta deja de ser sospechoso.
            assert espia.limpiezas == ["k"]

    async def test_se_comprueba_antes_de_buscar_el_codigo(self) -> None:
        """El orden importa —**se comprueba ANTES**—: si se comprobara después, el trabajo de buscar el
        código sería gratis para quien ya está castigado."""

        class Bloquea(TestLimiteDeIntentos.Espia):
            async def check(self, key: str) -> None:
                self.comprobados.append(key)
                raise RuntimeError("bloqueado")

        async with get_sessionmaker()() as s, s.begin():
            espia = Bloquea()
            with pytest.raises(RuntimeError):
                await redeem_session_code(
                    s,
                    code="ZZZZ9999",
                    code_verifier=VERIFIER,
                    limiter=espia,  # type: ignore[arg-type]
                    attempt_key="k",
                )
            # No llegó a contar el fallo porque no llegó a intentarlo.
            assert espia.fallos == []
