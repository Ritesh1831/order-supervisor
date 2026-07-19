"""Data contracts shared between the workflow and its activities.

Kept import-light on purpose: the workflow file imports this in its sandbox,
so nothing here may pull in IO libraries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Events the store emits. Terminal ones end the run by workflow rule.
KNOWN_EVENTS = [
    "order_created",
    "payment_confirmed",
    "payment_failed",
    "shipment_created",
    "shipment_delayed",
    "delivered",
    "cancelled",
]
TERMINAL_EVENTS = {"delivered", "cancelled"}

# The five business actions. Mocked as activity-log rows, nothing leaves the system.
BUSINESS_ACTIONS = [
    "send_customer_message",
    "create_internal_note",
    "escalate_issue",
    "mark_order_for_review",
    "request_human_review",
]


@dataclass
class SupervisorConfig:
    id: str
    name: str
    base_instruction: str
    enabled_actions: list[str]
    wake_config: dict[str, Any]  # {default_interval_s, aggressiveness, max_age_s}
    model: str


@dataclass
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowInput:
    run_id: str
    order_id: str
    supervisor: SupervisorConfig
    order_context: dict[str, Any]
    # Resume fields, populated only when the workflow continues-as-new.
    is_resume: bool = False
    resume_memory: str = ""
    resume_next_wakeup_iso: Optional[str] = None
    resume_instructions: list[str] = field(default_factory=list)
    resume_events_processed: int = 0
    resume_started_at_iso: Optional[str] = None


@dataclass
class TimelineItem:
    kind: str  # event | action | reasoning | note
    text: str


@dataclass
class AgentContext:
    """Everything the agent needs for one inference, assembled by the workflow."""
    run_id: str
    order_id: str
    trigger: str  # start | signal | scheduled | final
    base_instruction: str
    instructions: list[str]
    enabled_actions: list[str]
    memory_summary: str
    timeline_tail: list[TimelineItem]
    order_context: dict[str, Any]
    wake_config: dict[str, Any]
    model: str
    now_iso: str


@dataclass
class ActionRecord:
    name: str
    args: dict[str, Any]
    result: str


@dataclass
class AgentDecision:
    """What the agent proposes. The workflow decides what to honor."""
    reasoning: str = ""
    actions: list[ActionRecord] = field(default_factory=list)
    new_memory: Optional[str] = None
    sleep_seconds: Optional[int] = None
    next_wakeup_iso: Optional[str] = None
    recommend_completion: bool = False
    # Final-step output; only populated when trigger == "final".
    final_output: Optional[dict[str, Any]] = None
