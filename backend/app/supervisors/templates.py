"""Hardcoded supervisor templates. Seeded into the DB on startup and via seed.py.

Wake intervals are intentionally short so the sleep/wake behavior is visible in a
short demo/video. Bump `default_interval_s` / `max_sleep_s` for real workloads.
"""
from worker.shared.types import BUSINESS_ACTIONS

TEMPLATES = [
    {
        "id": "standard",
        "name": "Standard Order Supervisor",
        "base_instruction": (
            "You supervise a single e-commerce order from placement to delivery. "
            "Keep the customer informed, catch problems early, and escalate only when it matters. "
            "Prefer sleeping between checkpoints; do not act on routine progress."
        ),
        "enabled_actions": BUSINESS_ACTIONS,
        "wake_config": {
            "default_interval_s": 60,
            "max_sleep_s": 120,
            "aggressiveness": "medium",
            "max_age_s": 604800,
        },
        "model": "llama-3.3-70b-versatile",
    },
    {
        "id": "vip",
        "name": "VIP / High-Touch Supervisor",
        "base_instruction": (
            "This is a high-value customer. Be proactive and communicative. "
            "Send reassuring updates at each milestone and escalate any delay or payment issue immediately."
        ),
        "enabled_actions": BUSINESS_ACTIONS,
        "wake_config": {
            "default_interval_s": 45,
            "max_sleep_s": 180,
            "aggressiveness": "high",
            "max_age_s": 604800,
        },
        "model": "llama-3.3-70b-versatile",
    },
    {
        "id": "hands_off",
        "name": "Hands-Off Supervisor",
        "base_instruction": (
            "Minimize customer contact. Only intervene for failures (payment failed, "
            "cancellations, or serious delays). Never message the customer without a human review first."
        ),
        "enabled_actions": ["create_internal_note", "escalate_issue", "mark_order_for_review", "request_human_review"],
        "wake_config": {
            "default_interval_s": 90,
            "max_sleep_s": 300,
            "aggressiveness": "low",
            "max_age_s": 604800,
        },
        "model": "llama-3.3-70b-versatile",
    },
    {
        "id": "fraud_watch",
        "name": "Fraud & Payment Watch",
        "base_instruction": (
            "Guard against payment risk. Treat any payment failure or cancellation as urgent: "
            "flag the order for review and escalate. Never issue refunds or promises without a "
            "human review first. Stay quiet on healthy progress."
        ),
        "enabled_actions": ["create_internal_note", "escalate_issue", "mark_order_for_review", "request_human_review"],
        "wake_config": {
            "default_interval_s": 60,
            "max_sleep_s": 120,
            "aggressiveness": "high",
            "max_age_s": 604800,
        },
        "model": "llama-3.3-70b-versatile",
    },
    {
        "id": "logistics",
        "name": "Logistics-Focused Supervisor",
        "base_instruction": (
            "Focus on fulfillment and delivery. Watch shipment milestones closely; on any delay, "
            "proactively update the customer and escalate if it looks serious. Keep payment noise "
            "to a minimum."
        ),
        "enabled_actions": BUSINESS_ACTIONS,
        "wake_config": {
            "default_interval_s": 75,
            "max_sleep_s": 180,
            "aggressiveness": "medium",
            "max_age_s": 604800,
        },
        "model": "llama-3.3-70b-versatile",
    },
]
