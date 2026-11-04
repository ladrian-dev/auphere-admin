"""WP-06: the platform watcher detects each condition and notifies once.

Uses fakeredis for the counters the hot paths write, and monkeypatches the
notification sink so the tests assert on delivered alerts, not on email
infrastructure.
"""

from __future__ import annotations

import time
import uuid

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker.streams import platform_watcher as pw

pytestmark = pytest.mark.asyncio


@pytest.fixture
def delivered(monkeypatch) -> list[pw.Alert]:
    sink: list[pw.Alert] = []

    async def fake_notify(alert: pw.Alert) -> None:
        sink.append(alert)

    monkeypatch.setattr(pw, "_notify", fake_notify)
    return sink


async def test_dlq_entries_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xadd(pw.DLQ_STREAM, {"dlq_error": "boom"})

    out = await pw.process_tick(redis)

    kinds = [a.kind for a in out]
    assert "dlq_entries" in kinds
    assert delivered[0].count == 1


async def test_dedup_suppresses_second_tick(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xadd(pw.DLQ_STREAM, {"dlq_error": "boom"})

    first = await pw.process_tick(redis)
    second = await pw.process_tick(redis)

    assert [a.kind for a in first] == ["dlq_entries"]
    assert second == []  # same window → deduplicated


async def _old_entry(redis, *, age_s: float = 60 * 86_400, now: float | None = None) -> str:
    now = time.time() if now is None else now
    raw = await redis.xadd(
        pw.DLQ_STREAM, {"dlq_error": "boom"}, id=f"{int((now - age_s) * 1000)}-0"
    )
    return raw.decode() if isinstance(raw, bytes) else raw


async def _dlq_alerts(redis, *, now: float) -> list[pw.Alert]:
    return [a for a in await pw.process_tick(redis, now=now) if a.kind == "dlq_entries"]


async def test_old_entries_alert_once_and_then_stay_quiet(delivered) -> None:
    """Dos meses con la misma DLQ fueron 1630 registros y una alarma encendida
    para siempre. Una entrada de la que ya se avisó no vuelve a avisar."""
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    await _old_entry(redis, now=now)

    per_hour = [await _dlq_alerts(redis, now=now + hour * 3600) for hour in range(72)]

    assert [len(alerts) for alerts in per_hour] == [1] + [0] * 71


async def test_a_new_entry_alerts_although_old_ones_remain(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    await _old_entry(redis, now=now)
    await _dlq_alerts(redis, now=now)

    later = now + 30 * 86_400
    await _old_entry(redis, age_s=0, now=later)
    [alert] = await _dlq_alerts(redis, now=later + 60)

    assert alert.count == 1, "cuenta las nuevas, no todas"
    assert "1 entrada nueva" in alert.detail
    assert "2 en total" in alert.detail


async def test_it_says_what_to_do_with_the_command(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    await _old_entry(redis)

    [alert] = await _dlq_alerts(redis, now=time.time())

    assert "./scripts/ops/dlq.sh" in alert.detail
    assert " list" in alert.detail
    assert "docs/dlq.md" in alert.detail


@pytest.mark.parametrize(
    ("environment", "name"),
    [("production", "prod"), ("staging", "staging"), ("dev", "<entorno>")],
)
async def test_the_command_names_the_right_environment(environment: str, name: str) -> None:
    assert pw._dlq_command(environment) == f"./scripts/ops/dlq.sh {name} list"


async def test_it_counts_several_new_entries(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    await _old_entry(redis, now=now)
    await _dlq_alerts(redis, now=now)
    for index in range(3):
        await _old_entry(redis, age_s=-index, now=now + 3600)

    [alert] = await _dlq_alerts(redis, now=now + 7200)

    assert alert.count == 3
    assert "3 entradas nuevas" in alert.detail
    assert "4 en total" in alert.detail


async def test_discarding_old_entries_does_not_hide_a_new_one(delivered) -> None:
    """Contar con ``XLEN`` fallaría aquí: 25 descartadas y 1 nueva dan menos que antes."""
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    old = [await _old_entry(redis, age_s=86_400 - i, now=now) for i in range(3)]
    await _dlq_alerts(redis, now=now)

    await redis.xdel(pw.DLQ_STREAM, *old)
    await _old_entry(redis, age_s=0, now=now + 3600)

    assert len(await _dlq_alerts(redis, now=now + 3660)) == 1


async def test_discarding_the_newest_is_not_an_entry_that_arrived(delivered) -> None:
    """Sin comparar con la marca, la anterior pasaría a ser la «más nueva» y
    parecería recién llegada."""
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    await _old_entry(redis, age_s=7200, now=now)
    newest = await _old_entry(redis, age_s=3600, now=now)
    assert len(await _dlq_alerts(redis, now=now)) == 1

    await redis.xdel(pw.DLQ_STREAM, newest)

    assert await _dlq_alerts(redis, now=now + 7200) == []


async def test_an_emptied_dlq_stays_quiet_until_something_new_dies(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    entry = await _old_entry(redis, now=now)
    await _dlq_alerts(redis, now=now)

    await redis.xdel(pw.DLQ_STREAM, entry)
    assert await _dlq_alerts(redis, now=now + 3600) == []

    await _old_entry(redis, age_s=0, now=now + 7200)
    assert len(await _dlq_alerts(redis, now=now + 7260)) == 1


async def test_losing_the_mark_alerts_once_more_instead_of_going_silent(delivered) -> None:
    """Un Valkey restaurado o vaciado: ruido una vez, nunca silencio."""
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    await _old_entry(redis, now=now)
    await _dlq_alerts(redis, now=now)

    await redis.delete(pw.DLQ_MARK_KEY)
    for key in await redis.keys("nexus:alert:sent:dlq:*"):
        await redis.delete(key)

    assert len(await _dlq_alerts(redis, now=now + 86_400)) == 1
    assert await _dlq_alerts(redis, now=now + 2 * 86_400) == []


async def test_the_mark_moves_only_after_the_alert_went_out(monkeypatch) -> None:
    """Si el aviso no sale, la entrada sigue siendo nueva: mejor repetir que callar."""
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    entry = await _old_entry(redis, now=now)

    async def down(alert: pw.Alert) -> None:
        raise RuntimeError("el registro no acepta nada")

    monkeypatch.setattr(pw, "_notify", down)
    with pytest.raises(RuntimeError):
        await pw.process_tick(redis, now=now)
    assert await redis.get(pw.DLQ_MARK_KEY) is None

    sink: list[pw.Alert] = []

    async def fine(alert: pw.Alert) -> None:
        sink.append(alert)

    monkeypatch.setattr(pw, "_notify", fine)
    # El dedupe de una hora caduca solo en un Valkey de verdad; aquí se borra.
    await redis.delete(f"nexus:alert:sent:dlq:{entry}")
    await pw.process_tick(redis, now=now + 2 * pw.DEDUP_TTL_S)

    assert [a.kind for a in sink if a.kind == "dlq_entries"] == ["dlq_entries"]
    assert (await redis.get(pw.DLQ_MARK_KEY)).decode() == entry


async def test_a_failed_mark_repeats_the_alert_instead_of_losing_it(delivered, monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    await _old_entry(redis, now=now)
    real_set = redis.set

    async def no_mark(key, *args, **kwargs):
        if key == pw.DLQ_MARK_KEY:
            raise ConnectionError("valkey no contesta")
        return await real_set(key, *args, **kwargs)

    monkeypatch.setattr(redis, "set", no_mark)

    assert len(await _dlq_alerts(redis, now=now)) == 1, "el fallo de la marca no tumba la vuelta"
    assert await redis.get(pw.DLQ_MARK_KEY) is None


async def test_the_detail_carries_nothing_of_the_message(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xadd(
        pw.DLQ_STREAM,
        {
            "content": "quiero cancelar mi cita",
            "user_id": "34600111222",
            "tenant_id": str(uuid.uuid4()),
            "dlq_error": "value too long [parameters: ('+34600111222',)]",
        },
    )

    [alert] = await _dlq_alerts(redis, now=time.time())

    assert "34600111222" not in alert.detail
    assert "cancelar" not in alert.detail
    assert alert.tenant_id is None, "no avisa al negocio: es una alerta de la plataforma"


async def test_turn_error_burst_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    tenant = uuid.uuid4()
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:turn_errors:{tenant}:{window}", "6")

    out = await pw.process_tick(redis)

    burst = [a for a in out if a.kind == "turn_error_burst"]
    assert len(burst) == 1
    assert burst[0].tenant_id == tenant
    assert burst[0].count == 6


async def test_turn_errors_below_threshold_do_not_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:turn_errors:{uuid.uuid4()}:{window}", "5")

    out = await pw.process_tick(redis)
    assert [a for a in out if a.kind == "turn_error_burst"] == []


async def test_model_failures_of_the_tests_have_their_own_alert_and_no_whatsapp(
    monkeypatch,
) -> None:
    """Un partner que prueba su borrador no despierta al dueño del negocio: con
    ``tenant_id``, ``_notify`` escribe la fila que le manda el WhatsApp."""
    written: list[pw.Alert] = []

    async def fake_audit(alert: pw.Alert) -> None:
        written.append(alert)

    monkeypatch.setattr(pw, "_write_tenant_audit_row", fake_audit)
    redis = fakeaioredis.FakeRedis()
    tenant = uuid.uuid4()
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:simulated_model_failures:{tenant}:{window}", "6")

    out = await pw.process_tick(redis)

    (burst,) = [a for a in out if a.kind == "simulated_model_failure_burst"]
    assert burst.tenant_id is None
    assert burst.count == 6
    assert str(tenant) in burst.detail
    assert written == []
    assert [a for a in out if a.kind == "turn_error_burst"] == []
    assert await pw.process_tick(redis) == [], "una vez por ventana"


async def test_model_failures_of_the_tests_below_threshold_do_not_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:simulated_model_failures:{uuid.uuid4()}:{window}", "5")

    out = await pw.process_tick(redis)
    assert [a for a in out if a.kind == "simulated_model_failure_burst"] == []


async def test_meta_failure_burst_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:metafail:131047:{window}", "21")

    out = await pw.process_tick(redis)

    burst = [a for a in out if a.kind == "meta_failure_burst"]
    assert len(burst) == 1
    assert "131047" in burst[0].subject


async def test_cache_ratio_low_alert_with_volume(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    hour = int(time.time()) // 3600
    await redis.set(f"nexus:alert:llmtok:input:{hour}", "90000")
    await redis.set(f"nexus:alert:llmtok:cache_read:{hour}", "20000")

    out = await pw.process_tick(redis)

    assert [a.kind for a in out if a.kind == "cache_ratio_low"] == ["cache_ratio_low"]


async def test_cache_ratio_ignored_without_volume(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    hour = int(time.time()) // 3600
    await redis.set(f"nexus:alert:llmtok:input:{hour}", "500")
    await redis.set(f"nexus:alert:llmtok:cache_read:{hour}", "0")

    out = await pw.process_tick(redis)
    assert [a for a in out if a.kind == "cache_ratio_low"] == []


async def test_worker_dead_after_silence(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    # Last seen 10 minutes ago, no heartbeat key present.
    await redis.set("nexus:alert:worker_lastseen:nexus-worker", str(now - 600))

    out = await pw.process_tick(redis, now=now)

    dead = [a for a in out if a.kind == "worker_dead"]
    assert len(dead) == 1
    assert "nexus-worker" in dead[0].subject


async def test_worker_alive_no_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.set("nexus:health:nexus-worker:host-1", "1")

    out = await pw.process_tick(redis)
    assert [a for a in out if a.kind == "worker_dead"] == []


async def test_queue_backlog_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    # Entry delivered to a consumer 10 minutes ago and never acked. Craft the
    # entry id timestamp in the past so the age computation crosses 300s.
    old_ms = int((time.time() - 600) * 1000)
    await redis.xadd(pw.INBOUND_STREAM, {"content": "x"}, id=f"{old_ms}-0")
    await redis.xgroup_create(pw.INBOUND_STREAM, pw.INBOUND_GROUP, id="0")
    await redis.xreadgroup(
        groupname=pw.INBOUND_GROUP,
        consumername="c-dead",
        streams={pw.INBOUND_STREAM: ">"},
        count=1,
    )

    out = await pw.process_tick(redis)

    backlog = [a for a in out if a.kind == "queue_backlog"]
    assert len(backlog) == 1
    assert backlog[0].count == 1


async def test_the_burst_row_carries_a_target_so_it_is_written(monkeypatch) -> None:
    """``audit_log.target`` is NOT NULL. Without one the insert failed, the
    ``suppress`` around it swallowed the error and the row never existed."""
    import contextlib

    from nexus_api.core import tenant_context
    from nexus_api.db import base

    added: list = []

    class _Session:
        def add(self, row) -> None:
            added.append(row)

        async def commit(self) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

    monkeypatch.setattr(base, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(
        tenant_context, "tenant_scoped_session", lambda *_a, **_k: contextlib.nullcontext()
    )
    tenant = uuid.uuid4()
    alert = pw.Alert(
        kind="turn_error_burst", dedup_key="k", subject="s", detail="d", tenant_id=tenant, count=7
    )
    await pw._write_tenant_audit_row(alert)
    assert len(added) == 1
    assert added[0].target == f"tenant:{tenant}"
    assert added[0].action == "platform.turn_error_burst"


async def test_every_subject_says_auphere_not_nexus(delivered) -> None:
    """Spec 051 (catálogo §20): las alertas de plataforma dejan ``[Nexus]``."""
    redis = fakeaioredis.FakeRedis()
    await redis.xadd(pw.DLQ_STREAM, {"dlq_error": "boom"})
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:turn_errors:{uuid.uuid4()}:{window}", "6")
    await redis.set(f"nexus:alert:metafail:131047:{window}", "50")

    out = await pw.process_tick(redis)

    assert {a.kind for a in out} >= {"dlq_entries", "turn_error_burst", "meta_failure_burst"}
    for alert in out:
        assert alert.subject.startswith("[Auphere] "), alert.subject
        assert "[Nexus]" not in alert.subject


async def test_an_alert_is_logged_and_never_emailed(monkeypatch) -> None:
    """Spec 051, R9.1: la salud de la plataforma la vigila la monitorización
    (Datadog) por el registro; el correo enterraba lo que sí había que leer."""
    from structlog.testing import capture_logs

    sent: list[dict] = []

    async def _send(kind, **kw) -> bool:
        sent.append({"kind": kind, **kw})
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", _send)
    alert = pw.Alert(
        kind="dlq_entries",
        dedup_key="k",
        subject="[Auphere] Mensajes en la DLQ",
        detail="3 entradas en la DLQ",
        count=3,
    )

    with capture_logs() as logs:
        await pw._notify(alert)

    assert sent == []
    [event] = [e for e in logs if e["event"] == "platform_alert"]
    assert event["log_level"] == "error"
    assert (event["kind"], event["detail"]) == ("dlq_entries", "3 entradas en la DLQ")
