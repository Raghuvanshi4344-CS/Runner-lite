"""Example tests over the PROVIDED pieces, so `pytest` is green on a fresh checkout.

They also show the three shapes you'll want. Keep them or delete them — writing your own is
part of the exercise (TASK 6).
"""

from __future__ import annotations

import pytest

from dataclasses import replace

from app.autonomy import evaluate_gate
from app.agent import run_agent
from app.config import SETTINGS
from app.model_client import FatalError, MockModelClient, ThrottleError, complete_with_retry
from app.models import AgentIntent
from app.models import Effect, ExpectedEffect, Run, Task
from app.seed import CONTACTS
from app.seed import SCENARIOS
from app.tools import ToolError, Workspace
from app.verifier import verify
from tests.helpers import make_run


# Shape 1: a plain unit test. Arrange, act, assert.
def test_intent_parses_valid_json():
    intent = AgentIntent.model_validate_json('{"intent":"final","answer":"hi"}')
    assert intent.intent == "final"
    assert intent.answer == "hi"


# Shape 2: asserting that something correctly REFUSES. Easy to forget, often where the bugs are.
def test_intent_rejects_tool_use_without_a_tool():
    with pytest.raises(Exception):
        AgentIntent.model_validate_json('{"intent":"tool_use","thought":"hmm"}')


# Shape 3: a table-driven test. One case per row, and pytest reports each row separately, so a
# failure tells you exactly which input broke. Ideal for TASK 1's decision table.
@pytest.mark.parametrize(
    "query,expected_id",
    [
        ("acme", "c_1"),
        ("globex", "c_2"),
        ("initech", "c_3"),
    ],
)
def test_search_finds_contacts(query, expected_id):
    ws = Workspace(CONTACTS)
    found = ws.search_contacts(query=query)
    assert [c["id"] for c in found] == [expected_id]


def test_read_tool_raises_for_a_missing_contact():
    ws = Workspace(CONTACTS)
    with pytest.raises(ToolError):
        ws.get_contact(contact_id="c_nope")


@pytest.mark.parametrize(
    "level,tool_kind,writes_so_far,expected",
    [
        ("shadow", "read", 0, (True, False, False)),
        ("supervised", "read", 0, (True, False, False)),
        ("autonomous", "read", 2, (True, False, False)),
        ("shadow", "write", 0, (True, True, False)),
        ("supervised", "write", 0, (False, False, True)),
        ("autonomous", "write", 1, (True, False, False)),
        ("autonomous", "write", 2, (False, False, True)),
    ],
)
def test_gate_decision_table(level, tool_kind, writes_so_far, expected):
    decision = evaluate_gate(level, tool_kind, writes_so_far, max_auto_writes=2)
    assert (decision.allow, decision.simulate, decision.requires_approval) == expected
    assert decision.reason


def test_verifier_passes_matching_effects():
    task = Task(
        id="t",
        goal="send",
        expected_effects=[ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})],
    )
    run = Run(
        id="r",
        task_id="t",
        autonomy="autonomous",
        effects=[Effect(tool="send_message", args={"contact_id": "c_1", "body": "hi"})],
    )
    verdict = verify(task, run)
    assert verdict.passed is True
    assert len(verdict.matched) == 1


def test_verifier_reports_missing_and_does_not_reuse_effects():
    expected = [ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})] * 2
    task = Task(id="t", goal="send twice", expected_effects=expected)
    run = Run(
        id="r",
        task_id="t",
        autonomy="autonomous",
        effects=[Effect(tool="send_message", args={"contact_id": "c_1"})],
    )
    verdict = verify(task, run)
    assert verdict.passed is False
    assert len(verdict.matched) == 1
    assert len(verdict.missing) == 1


def test_verifier_reports_unexpected_effects():
    task = Task(id="t", goal="send", expected_effects=[])
    run = Run(
        id="r",
        task_id="t",
        autonomy="autonomous",
        effects=[Effect(tool="send_message", args={"contact_id": "c_2"})],
    )
    verdict = verify(task, run)
    assert verdict.passed is False
    assert len(verdict.unexpected) == 1


def test_retry_repeats_throttled_calls():
    model = MockModelClient([ThrottleError("429"), ThrottleError("429"), "ok"])
    settings = replace(SETTINGS, model_max_retries=2, model_backoff_base_seconds=0)
    assert complete_with_retry(model, [], settings) == "ok"
    assert model.calls == 3


def test_retry_does_not_repeat_fatal_calls():
    model = MockModelClient([FatalError("bad key"), "ok"])
    with pytest.raises(FatalError):
        complete_with_retry(model, [], replace(SETTINGS, model_backoff_base_seconds=0))
    assert model.calls == 1


def test_send_message_is_idempotent():
    ws = Workspace(CONTACTS)
    first = ws.send_message(contact_id="c_1", body="hello", idempotency_key="r:1")
    second = ws.send_message(contact_id="c_1", body="hello", idempotency_key="r:1")
    assert first["message_id"] == second["message_id"]
    assert second["deduped"] is True
    assert len(ws.messages) == 1


def test_agent_completes_and_verifies_a_write():
    run, deps = make_run(
        SCENARIOS["send_followup"],
        expected=[ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})],
    )
    result = run_agent(run, deps)
    assert result.status == "completed"
    assert result.verdict is not None and result.verdict.passed is True
    assert len(result.effects) == 1


def test_shadow_agent_records_effect_without_mutating_workspace():
    run, deps = make_run(
        SCENARIOS["send_followup"],
        autonomy="shadow",
        expected=[ExpectedEffect(tool="send_message", match={"contact_id": "c_1"})],
    )
    result = run_agent(run, deps)
    assert result.status == "completed"
    assert result.effects[0].simulated is True
    assert deps.workspace.messages == []


@pytest.mark.parametrize("scenario", ["unknown_tool", "tool_error"])
def test_agent_recovers_from_tool_problems(scenario):
    run, deps = make_run(SCENARIOS[scenario])
    result = run_agent(run, deps)
    assert result.status == "completed"
    assert result.verdict is not None and result.verdict.passed is True


def test_agent_fails_when_model_never_finishes():
    run, deps = make_run(
        SCENARIOS["never_finishes"],
        settings=replace(SETTINGS, max_steps=3),
    )
    result = run_agent(run, deps)
    assert result.status == "failed"
    assert result.error == "maximum steps reached"


def test_agent_handles_fatal_model_error():
    run, deps = make_run(SCENARIOS["bad_credentials"])
    result = run_agent(run, deps)
    assert result.status == "failed"
    assert result.error == "401 invalid api key"
    assert deps.model.calls == 1


def test_start_run_endpoint_returns_finished_run(client):
    task = client.post(
        "/api/v1/tasks",
        json={"goal": "follow up", "scenario": "default", "autonomy": "autonomous"},
    ).json()
    response = client.post("/api/v1/runs", json={"task_id": task["id"]})
    assert response.status_code == 201
    assert response.json()["status"] == "completed"
