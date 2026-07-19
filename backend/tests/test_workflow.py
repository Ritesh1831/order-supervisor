"""Integration tests for the supervisor workflow.

They spin up Temporal's local dev server (downloaded on first run) with an in-memory
DB stub and a fake LLM provider — no Docker, no Groq key. If the test server can't
start (e.g. offline), the tests skip rather than fail.
"""
import asyncio
import uuid

import pytest

from app import db  # noqa: E402
import worker.activities as activities_mod  # noqa: E402
import worker.agent.runtime as runtime_mod  # noqa: E402
from worker.agent.llm.base import LLMResponse, ToolCall  # noqa: E402
from worker.shared.types import SupervisorConfig, WorkflowInput  # noqa: E402
from worker.workflows import OrderSupervisorWorkflow  # noqa: E402

ACT: list = []
RUN: dict = {}


def _tc(name, args):
    return ToolCall(id=str(uuid.uuid4()), name=name, arguments=args)


class FakeProvider:
    """Deterministic stand-in for Groq so tests need no key and no network."""

    def __init__(self, model=None):
        pass

    async def chat(self, messages, tools=None):
        if not tools:  # compact_memory / classify: plain-text answer expected
            return LLMResponse(content="Rolling summary of the order so far.")
        if messages and messages[-1].get("role") == "tool":
            return LLMResponse(content="", tool_calls=[_tc("finish", {})])
        text = messages[-1]["content"] if messages else ""
        if "final report" in text.lower() or "run is ending" in text.lower():
            return LLMResponse(content="", tool_calls=[_tc("submit_final_report", {
                "summary": "Order handled to completion with minimal intervention.",
                "key_actions": ["monitored the lifecycle"],
                "learnings": ["routine progress rarely needs action"],
                "recommendations": ["keep the standard wake cadence"],
            })])
        return LLMResponse(content="Reviewed order state; nothing urgent.", tool_calls=[
            _tc("update_memory", {"summary": "Watching order; last review nominal."}),
            _tc("sleep", {"seconds": 1800}),
        ])


@pytest.fixture(autouse=True)
def stub_env(monkeypatch):
    ACT.clear()
    RUN.clear()

    async def add_activity(run_id, type_, title, payload=None):
        ACT.append({"type": type_, "title": title, "payload": payload or {}})

    async def update_run(run_id, **fields):
        RUN.setdefault(run_id, {}).update(fields)

    async def noop(*a, **k):
        pass

    monkeypatch.setattr(db, "add_activity", add_activity)
    monkeypatch.setattr(db, "update_run", update_run)
    monkeypatch.setattr(db, "init_schema", noop)
    monkeypatch.setattr(runtime_mod, "make_provider", lambda model=None: FakeProvider())
    monkeypatch.setattr(activities_mod, "make_provider", lambda model=None: FakeProvider())


def _input(run_id: str, **wake) -> WorkflowInput:
    cfg = {"aggressiveness": "medium", "max_age_s": 604800, **wake}
    return WorkflowInput(
        run_id=run_id,
        order_id=run_id,
        supervisor=SupervisorConfig("standard", "S", "Supervise.", ["escalate_issue"], cfg, "test"),
        order_context={"total": 49},
    )


async def _worker_env():
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker
    from worker.worker import ACTIVITIES

    try:
        env = await WorkflowEnvironment.start_local()
    except Exception as e:  # offline / binary unavailable
        pytest.skip(f"local Temporal server unavailable: {e}")
    worker = Worker(env.client, task_queue="test-q", workflows=[OrderSupervisorWorkflow], activities=ACTIVITIES)
    return env, worker


@pytest.mark.asyncio
async def test_lifecycle_triggers_classifier_and_completion():
    env, worker = await _worker_env()
    async with worker:
        rid = f"order-{uuid.uuid4().hex[:6]}"
        h = await env.client.start_workflow(
            OrderSupervisorWorkflow.run, _input(rid), id=rid, task_queue="test-q"
        )
        # the start inference runs asynchronously; wait for it to schedule the first wake-up
        for _ in range(50):
            st = await h.query("get_state")
            if st["next_wakeup"]:
                break
            await asyncio.sleep(0.1)
        assert st["status"] == "running" and st["next_wakeup"]

        await h.signal("submit_event", {"type": "payment_confirmed", "payload": {}})
        await h.signal("submit_event", {"type": "shipment_delayed", "payload": {}})
        await h.signal("add_instruction", "If shipment is delayed, escalate immediately.")
        await h.signal("submit_event", {"type": "delivered", "payload": {}})

        result = await h.result()
    await env.shutdown()

    decisions = [a["title"] for a in ACT if a["type"] == "wake_decision"]
    assert result["status"] == "completed"
    assert any("SLEEP: payment_confirmed" in d for d in decisions)   # routine -> stays asleep
    assert any("WAKE: shipment_delayed" in d for d in decisions)     # critical -> wakes agent
    assert any(a["type"] == "final" for a in ACT)                    # final report produced

    final = RUN.get(rid, {}).get("final_output")
    assert final and final["summary"]                                # structured report saved
    assert set(final) >= {"summary", "key_actions", "learnings", "recommendations"}


@pytest.mark.asyncio
async def test_continue_as_new_and_compaction():
    env, worker = await _worker_env()
    async with worker:
        rid = f"order-{uuid.uuid4().hex[:6]}"
        inp = _input(rid, continue_as_new_every=5)  # low threshold so the test is fast
        h = await env.client.start_workflow(
            OrderSupervisorWorkflow.run, inp, id=rid, task_queue="test-q"
        )
        for _ in range(7):  # push past the rollover threshold
            await h.signal("submit_event", {"type": "payment_confirmed", "payload": {}})

        # wait for the rollover before ending the run (otherwise a terminal event drained
        # in the same batch would pre-empt the continue_as_new check)
        for _ in range(50):
            if any(a["title"] == "memory compacted" for a in ACT):
                break
            await asyncio.sleep(0.1)
        assert any(a["title"] == "memory compacted" for a in ACT)  # compacted before rollover

        await h.signal("submit_event", {"type": "delivered", "payload": {}})
        result = await h.result()
    await env.shutdown()

    assert result["status"] == "completed"
