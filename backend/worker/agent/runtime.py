from __future__ import annotations

from typing import Any

from app import db
from worker.agent.llm.base import ToolCall
from worker.agent.llm.factory import make_provider
from worker.agent.prompts import context_prompt, final_prompt, system_prompt
from worker.agent.tools import (
    build_tool_schemas,
    is_business_action,
    run_business_action,
)
from worker.shared.types import AgentContext, AgentDecision

MAX_TURNS = 5


async def run_inference(ctx: AgentContext) -> AgentDecision:
    provider = make_provider(ctx.model)
    is_final = ctx.trigger == "final"
    tools = build_tool_schemas(ctx.enabled_actions, is_final)

    user = context_prompt(ctx) + ("\n\n" + final_prompt() if is_final else "")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(ctx)},
        {"role": "user", "content": user},
    ]

    decision = AgentDecision()
    prose: list[str] = []

    try:
        for _ in range(MAX_TURNS):
            resp = await provider.chat(messages, tools)
            if resp.content:
                prose.append(resp.content)

            if not resp.tool_calls:
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": resp.content or "",
                    "tool_calls": [_openai_call(tc) for tc in resp.tool_calls],
                }
            )
            stop = False
            for tc in resp.tool_calls:
                result = await _handle(tc, ctx, decision)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                if tc.name == "finish":
                    stop = True
            if stop:
                break
    except Exception as e:
        # Never wedge the run on an LLM error: log it, retry soon, keep going.
        await db.add_activity(ctx.run_id, "reasoning", "agent error (degraded)", {"error": str(e)[:500]})
        decision.reasoning = f"LLM unavailable: {e}. Will retry shortly."
        if decision.sleep_seconds is None and not decision.next_wakeup_iso:
            decision.sleep_seconds = 60
        if is_final:
            decision.final_output = {
                "summary": ctx.memory_summary or "Run ended; final report unavailable (LLM error).",
                "key_actions": [a.name for a in decision.actions],
                "learnings": [],
                "recommendations": [],
            }
        return decision

    text = " ".join(p.strip() for p in prose if p.strip())
    decision.reasoning = text
    # If the model ended the final step without calling submit_final_report, synthesize one.
    if is_final and not decision.final_output:
        decision.final_output = {
            "summary": text or decision.new_memory or ctx.memory_summary,
            "key_actions": [a.name for a in decision.actions],
            "learnings": [],
            "recommendations": [],
        }
    return decision


async def _handle(tc: ToolCall, ctx: AgentContext, decision: AgentDecision) -> str:
    name, args = tc.name, tc.arguments or {}

    if is_business_action(name):
        record = run_business_action(name, args)
        decision.actions.append(record)
        await db.add_activity(ctx.run_id, "action", name, {"args": args, "result": record.result})
        return record.result

    if name == "update_memory":
        decision.new_memory = args.get("summary", "")
        return "memory updated"
    if name == "sleep":
        decision.sleep_seconds = int(args.get("seconds", 3600))
        return f"will sleep {decision.sleep_seconds}s"
    if name == "schedule_next_wakeup":
        decision.next_wakeup_iso = args.get("when_iso")
        return f"next wake-up {decision.next_wakeup_iso}"
    if name == "recommend_completion":
        decision.recommend_completion = True
        return "completion recommended"
    if name == "submit_final_report":
        decision.final_output = {
            "summary": args.get("summary", ""),
            "key_actions": args.get("key_actions", []),
            "learnings": args.get("learnings", []),
            "recommendations": args.get("recommendations", []),
        }
        return "final report recorded"
    if name == "finish":
        return "ok"
    return f"unknown tool {name}"


def _openai_call(tc: ToolCall) -> dict[str, Any]:
    import json

    return {
        "id": tc.id,
        "type": "function",
        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments or {})},
    }
