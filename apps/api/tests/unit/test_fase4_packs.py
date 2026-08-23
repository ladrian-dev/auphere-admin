"""Unit: parent node names stay fixed; pack parse; no rename API."""

from __future__ import annotations

import inspect

import pytest
from nexus_worker.runtime.packs.graph import PARENT_NODE_NAMES, compile_parent_graph
from pydantic import ValidationError

from nexus_api.packs.schema import WorkflowPackIn, parse_workflow_body


def test_parent_node_names_are_fixed() -> None:
    assert PARENT_NODE_NAMES == ("send_template", "wait_reply", "end")
    compiled = compile_parent_graph()
    names = set(compiled.get_graph().nodes)
    for node in PARENT_NODE_NAMES:
        assert node in names


def test_compile_parent_graph_has_no_rename_parameter() -> None:
    sig = inspect.signature(compile_parent_graph)
    assert "rename" not in sig.parameters
    assert "node_names" not in sig.parameters


def test_partner_id_in_yaml_field_is_rejected() -> None:
    body = WorkflowPackIn.model_validate(
        {
            "yaml": {
                "trigger": "event",
                "steps": ["end"],
                "partner_id": "x",
            }
        }
    )
    with pytest.raises(ValidationError):
        parse_workflow_body(body)


def test_yaml_string_parses() -> None:
    body = WorkflowPackIn.model_validate({"yaml": ("trigger: event\nsteps:\n  - end\nstop: end\n")})
    spec = parse_workflow_body(body)
    assert spec.trigger == "event"
    assert spec.steps == ["end"]
