import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from temporalio.exceptions import WorkflowAlreadyStartedError

from app import db
from app.config import TEMPORAL_TASK_QUEUE
from app.temporal_client import get_client
from worker.shared.types import SupervisorConfig, WorkflowInput

TERMINAL_STATUSES = {"completed", "terminated"}

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunIn(BaseModel):
    supervisor_id: str
    order_id: str | None = None
    order_context: dict[str, Any] = Field(default_factory=dict)


class EventIn(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class InstructionIn(BaseModel):
    text: str


class TerminateIn(BaseModel):
    reason: str = "manual"


@router.get("")
async def list_runs():
    return await db.list_runs()


@router.post("")
async def create_run(body: RunIn):
    sup = await db.get_supervisor(body.supervisor_id)
    if not sup:
        raise HTTPException(404, "supervisor not found")

    order_id = body.order_id or f"ORD-{str(uuid.uuid4())[:6].upper()}"
    run_id = f"order-{order_id}"  # run_id == workflow_id: one workflow per order
    order_context = body.order_context or _demo_order(order_id)

    await db.create_run(run_id, order_id, sup["id"], run_id, order_context)

    wf_input = WorkflowInput(
        run_id=run_id,
        order_id=order_id,
        supervisor=SupervisorConfig(
            id=sup["id"],
            name=sup["name"],
            base_instruction=sup["base_instruction"],
            enabled_actions=sup["enabled_actions"],
            wake_config=sup["wake_config"],
            model=sup["model"],
        ),
        order_context=order_context,
    )

    client = await get_client()
    try:
        await client.start_workflow(
            "OrderSupervisorWorkflow",
            wf_input,
            id=run_id,
            task_queue=TEMPORAL_TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError:
        raise HTTPException(409, f"a run for order '{order_id}' already exists")
    return await db.get_run(run_id)


@router.get("/{run_id}")
async def get_run(run_id: str):
    run = await db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    run["activities"] = await db.list_activities(run_id)
    return run


@router.get("/{run_id}/activities")
async def get_activities(run_id: str):
    return await db.list_activities(run_id)


@router.get("/{run_id}/state")
async def get_state(run_id: str):
    client = await get_client()
    handle = client.get_workflow_handle(run_id)
    try:
        return await handle.query("get_state")
    except Exception as e:
        raise HTTPException(409, f"workflow not queryable: {e}")


@router.post("/{run_id}/events")
async def send_event(run_id: str, body: EventIn):
    await _signal(run_id, "submit_event", {"type": body.type, "payload": body.payload})
    return {"ok": True}


@router.post("/{run_id}/instructions")
async def add_instruction(run_id: str, body: InstructionIn):
    await _signal(run_id, "add_instruction", body.text)
    return {"ok": True}


@router.post("/{run_id}/interrupt")
async def interrupt(run_id: str):
    await _signal(run_id, "interrupt")
    return {"ok": True}


@router.post("/{run_id}/pause")
async def pause(run_id: str):
    await _signal(run_id, "pause")
    return {"ok": True}


@router.post("/{run_id}/resume")
async def resume(run_id: str):
    await _signal(run_id, "resume")
    return {"ok": True}


@router.post("/{run_id}/terminate")
async def terminate(run_id: str, body: TerminateIn):
    await _signal(run_id, "terminate_run", body.reason)
    return {"ok": True}


async def _signal(run_id: str, name: str, *args: Any) -> None:
    run = await db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run["status"] in TERMINAL_STATUSES:
        raise HTTPException(409, f"run is {run['status']}; cannot accept '{name}'")
    client = await get_client()
    handle = client.get_workflow_handle(run_id)
    try:
        await handle.signal(name, *args)
    except Exception as e:
        raise HTTPException(409, f"could not deliver '{name}': {e}")


def _demo_order(order_id: str) -> dict[str, Any]:
    return {
        "order_id": order_id,
        "customer": "Demo Customer",
        "items": [{"sku": "WIDGET-1", "qty": 1}],
        "total": 49.0,
        "currency": "USD",
    }
