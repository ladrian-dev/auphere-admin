"""Requisito 10 — lo que gasta se mide, y lo que no gasta no se cobra.

Dos afirmaciones, y la segunda es tan importante como la primera:

* El **modelo** que consume una sesión local entra en el mismo medidor que ve el
  partner. No hay un contador aparte para esto: dos contadores es un sitio donde
  las cifras dejan de cuadrar.
* El **reloj de máquina no se factura**. La máquina es del partner y ya está
  pagada — es literalmente la ventaja económica de esta superficie frente a la
  VM, donde los 121 $/mes/partner salen de facturar reloj.
"""

from __future__ import annotations

import inspect
import uuid

from nexus_api.services import local_workstation_metering as metering


def test_the_idempotency_key_is_derived_from_the_execution():
    """Un resultado que llega dos veces no cobra dos veces."""
    execution_id = uuid.uuid4()
    assert metering.idempotency_key_for(execution_id) == metering.idempotency_key_for(execution_id)
    assert str(execution_id) in metering.idempotency_key_for(execution_id)


def test_two_executions_are_two_keys():
    assert metering.idempotency_key_for(uuid.uuid4()) != metering.idempotency_key_for(uuid.uuid4())


def test_the_key_is_namespaced_so_it_cannot_collide_with_another_lane():
    key = metering.idempotency_key_for(uuid.uuid4())
    assert key.startswith(metering.KEY_PREFIX)
    assert metering.KEY_PREFIX.startswith("local_exec")


def test_machine_clock_is_never_charged():
    """No hay parámetro de duración: no se puede facturar reloj ni por error."""
    signature = inspect.signature(metering.meter_local_model_use)
    params = set(signature.parameters)
    for forbidden in ("duration", "duration_ms", "seconds", "elapsed", "wall_clock"):
        assert forbidden not in params, f"{forbidden} abriría la puerta a facturar reloj"


def test_it_meters_model_use_and_says_so():
    assert "model" in metering.meter_local_model_use.__name__


def test_nothing_is_charged_for_a_denied_execution():
    """Una denegación no consumió modelo: cobrarla sería cobrar por decir que no."""
    assert metering.chargeable_units(outcome="denegada", model_units=5) == 0
    assert metering.chargeable_units(outcome="completada", model_units=5) == 5
    assert metering.chargeable_units(outcome="expirada", model_units=5) == 5
