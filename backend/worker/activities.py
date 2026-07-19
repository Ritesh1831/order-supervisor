from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from temporalio import activity

from app import db
from worker.agent.llm.factory import make_provider
from worker.agent.runtime import run_inference
from worker.shared.types import AgentContext, AgentDecision


@activity.defn
async def log_activity(run_id: str, type_: str, title: str, payload: dict[str, Any]) -> None:
    await db.add_activity(run_id, type_, title, payload)


@activity.defn
async def sync_run_state(
    run_id: str,
    status: str,
    next_wakeup_iso: Optional[str],
    sleep_state: str,
    memory_summary: str,
) -> None:
    next_wakeup = datetime.fromisoformat(next_wakeup_iso) if next_wakeup_iso else None
    await db.update_run(
        run_id,
        status=status,
        next_wakeup=next_wakeup,
        sleep_state=sleep_state,
        memory_summary=memory_summary,
    )


@activity.defn
async def agent_inference(ctx: AgentContext) -> AgentDecision:
    return await run_inference(ctx)


@activity.defn
async def classify_unknown_event(event_type: str, payload: dict[str, Any], aggr: str) -> bool:
    provider = make_provider()
    prompt = (
        "You gate an order supervisor agent. Reply with only 'wake' or 'sleep'. "
        f"Aggressiveness={aggr}. An event just arrived that we don't have a rule for: "
        f"type={event_type}, payload={payload}. Should the supervisor wake now?"
    )
    try:
        resp = await provider.chat(
            [{"role": "user", "content": prompt}], tools=None
        )
        return "wake" in resp.content.lower()
    except Exception:
        return True  # unknown + can't classify -> escalate to be safe


@activity.defn
async def compact_memory(
    run_id: str, current_summary: str, old_items: list[dict[str, Any]]
) -> str:
    lines = "\n".join(f"- [{i.get('kind')}] {i.get('text')}" for i in old_items)
    prompt = (
        "Maintain a compact rolling memory for an order supervisor. "
        "Merge the existing summary with these older timeline items into a concise summary "
        "(<=120 words) that preserves decisions, open issues, and customer-facing actions.\n\n"
        f"Existing summary:\n{current_summary or '(none)'}\n\nOlder items:\n{lines}"
    )
    provider = make_provider()
    try:
        resp = await provider.chat([{"role": "user", "content": prompt}], tools=None)
        new = resp.content.strip()
    except Exception:
        new = current_summary
    merged = new or current_summary
    await db.add_activity(run_id, "memory_update", "memory compacted", {"summary": merged})
    return merged


@activity.defn
async def save_final_output(run_id: str, final_output: dict[str, Any]) -> None:
    await db.update_run(run_id, final_output=final_output)


@activity.defn
async def finalize_run(run_id: str, status: str) -> None:
    await db.update_run(run_id, status=status, sleep_state="done", next_wakeup=None)
