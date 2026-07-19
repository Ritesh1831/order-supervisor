from __future__ import annotations

from worker.shared.types import AgentContext

_TRIGGER_NOTE = {
    "start": "The run just started. Assess the order and decide an initial plan and next check-in.",
    "signal": "A new event or instruction arrived. Decide whether to act, then set the next check-in.",
    "scheduled": "This is a scheduled review. Check whether anything needs attention, then sleep again.",
    "final": "The run is ending. Produce a final report only. Do not take business actions.",
}


def system_prompt(ctx: AgentContext) -> str:
    return (
        "You are an autonomous supervisor for a single e-commerce order. "
        "You wake occasionally, decide whether to act, and sleep in between. "
        "Do not act on routine progress; intervene only when it genuinely helps the customer "
        "or the order.\n\n"
        f"SUPERVISOR INSTRUCTION:\n{ctx.base_instruction}\n\n"
        "Each turn:\n"
        "1. Briefly state your assessment of the order's current state (this is your reasoning).\n"
        "2. Take business actions only when warranted; obey any run-specific instructions exactly.\n"
        "3. Call `update_memory` when something worth remembering changed.\n"
        "4. Decide when to check back: sooner if a problem is open, later if all is calm. "
        "End by calling `sleep` (seconds) or `schedule_next_wakeup`, then `finish`.\n"
        "Payments can arrive in installments: add up the confirmed amounts so far and only treat "
        "payment as short if the running total is still below the order total.\n"
        "Keep customer messages short and specific. Escalate real problems rather than guessing."
    )


def final_prompt() -> str:
    return (
        "The run is ending. Call `submit_final_report` exactly once, then `finish`. "
        "Be specific and grounded in THIS order — reference the actual events, amounts, and "
        "timing from the timeline and memory, not generic statements.\n"
        "- summary: what actually happened to this order, start to finish.\n"
        "- key_actions: the concrete actions you took (what and why).\n"
        "- learnings: what this specific run revealed (e.g. where the delay came from).\n"
        "- recommendations: concrete, actionable next steps for a similar order — avoid platitudes "
        "like 'keep communicating'.\n"
        "Do not take any other actions."
    )


def context_prompt(ctx: AgentContext) -> str:
    lines = [
        f"Trigger: {ctx.trigger} — {_TRIGGER_NOTE.get(ctx.trigger, '')}",
        f"Now: {ctx.now_iso}",
        f"Order: {ctx.order_id}",
        f"Order context: {ctx.order_context}",
        f"Wake config: {ctx.wake_config}",
    ]
    if ctx.instructions:
        lines.append("Run-specific instructions (obey these):")
        lines += [f"  - {i}" for i in ctx.instructions]
    lines.append(f"\nMemory summary:\n{ctx.memory_summary or '(none yet)'}")
    if ctx.timeline_tail:
        lines.append("\nRecent timeline:")
        lines += [f"  - [{t.kind}] {t.text}" for t in ctx.timeline_tail]
    return "\n".join(lines)
