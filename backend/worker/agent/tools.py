"""Tool schemas exposed to the LLM plus their local executors.

Two families:
  - business actions -> write an activity row (mocked side effects)
  - control tools -> fold into the AgentDecision; the workflow enforces them
"""
from __future__ import annotations

from typing import Any

from worker.shared.types import ActionRecord

BUSINESS_TOOL_DEFS = {
    "send_customer_message": {
        "description": "Send a message to the customer. Use sparingly and only when it adds value.",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    },
    "create_internal_note": {
        "description": "Record an internal note for the ops team.",
        "properties": {"note": {"type": "string"}},
        "required": ["note"],
    },
    "escalate_issue": {
        "description": "Escalate a problem to a human operator.",
        "properties": {"reason": {"type": "string"}, "severity": {"type": "string"}},
        "required": ["reason"],
    },
    "mark_order_for_review": {
        "description": "Flag this order for manual review.",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
    },
    "request_human_review": {
        "description": "Ask a human to review before any customer contact.",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    },
}

CONTROL_TOOL_DEFS = {
    "update_memory": {
        "description": "Replace the compact memory summary with an updated one.",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    },
    "sleep": {
        "description": "Go back to sleep for N seconds until the next scheduled review.",
        "properties": {"seconds": {"type": "integer"}},
        "required": ["seconds"],
    },
    "schedule_next_wakeup": {
        "description": "Schedule the next review at an absolute ISO-8601 timestamp.",
        "properties": {"when_iso": {"type": "string"}},
        "required": ["when_iso"],
    },
    "recommend_completion": {
        "description": "Recommend the run be completed (non-binding; workflow rules decide).",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
    },
    "submit_final_report": {
        "description": "Provide the end-of-run report. Call this once on the final step.",
        "properties": {
            "summary": {"type": "string", "description": "What happened over the run."},
            "key_actions": {"type": "array", "items": {"type": "string"}},
            "learnings": {"type": "array", "items": {"type": "string"}},
            "recommendations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary"],
    },
    "finish": {
        "description": "Stop taking actions this turn.",
        "properties": {},
        "required": [],
    },
}

# Tools offered on the final step only — the run is ending, so no acting or sleeping.
FINAL_TOOLS = ["submit_final_report", "finish"]


def build_tool_schemas(enabled_actions: list[str], is_final: bool) -> list[dict[str, Any]]:
    if is_final:
        names = FINAL_TOOLS
    else:
        control = [n for n in CONTROL_TOOL_DEFS if n not in ("submit_final_report",)]
        names = [a for a in enabled_actions if a in BUSINESS_TOOL_DEFS] + control
    defs = {**BUSINESS_TOOL_DEFS, **CONTROL_TOOL_DEFS}
    schemas = []
    for name in names:
        d = defs[name]
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": d["description"],
                    "parameters": {
                        "type": "object",
                        "properties": d["properties"],
                        "required": d["required"],
                    },
                },
            }
        )
    return schemas


def is_business_action(name: str) -> bool:
    return name in BUSINESS_TOOL_DEFS


def run_business_action(name: str, args: dict[str, Any]) -> ActionRecord:
    """Mocked execution: nothing leaves the system, we just describe what happened."""
    summary = {
        "send_customer_message": lambda a: f"message sent: {a.get('message', '')}",
        "create_internal_note": lambda a: f"note: {a.get('note', '')}",
        "escalate_issue": lambda a: f"escalated ({a.get('severity', 'normal')}): {a.get('reason', '')}",
        "mark_order_for_review": lambda a: f"flagged for review: {a.get('reason', '')}",
        "request_human_review": lambda a: f"human review requested: {a.get('question', '')}",
    }[name](args)
    return ActionRecord(name=name, args=args, result=summary)
