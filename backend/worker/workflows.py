from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from worker.shared.types import (
        TERMINAL_EVENTS,
        AgentContext,
        AgentDecision,
        Event,
        TimelineItem,
        WorkflowInput,
    )

# Fallback cap on any sleep if a supervisor doesn't set wake_config.max_sleep_s,
# so a run never goes fully dark.
DEFAULT_MAX_SLEEP_S = 300
DEFAULT_INTERVAL_S = 60
# Compact once the in-memory tail grows past this.
TAIL_LIMIT = 12
# Roll history into a fresh run after this many processed events.
CONTINUE_AS_NEW_EVERY = 40

_RETRY = RetryPolicy(maximum_attempts=4)


@workflow.defn
class OrderSupervisorWorkflow:
    def __init__(self) -> None:
        self._input: Optional[WorkflowInput] = None
        self._status = "running"
        self._paused = False
        self._terminal = False
        self._terminate_reason = ""
        self._wake_now = False
        self._pending_events: list[Event] = []
        self._pending_instructions: list[str] = []
        self._instructions: list[str] = []
        self._memory_summary = ""
        self._timeline_tail: list[TimelineItem] = []
        self._next_wakeup_iso: Optional[str] = None
        self._events_processed = 0
        self._started_at_iso = ""

    # ------------------------------------------------------------------ run
    @workflow.run
    async def run(self, arg: WorkflowInput) -> dict[str, Any]:
        first_start = self._load(arg)

        if first_start:
            await self._act("lifecycle", "run started", {"order_id": self._input.order_id})
            # The run represents an already-placed order; record it as the opening event.
            await self._act("event", "order_created", self._input.order_context)
            self._timeline_tail.append(TimelineItem("event", "order_created"))
            await self._run_agent("start")

        while not self._terminal:
            await self._sleep()

            if self._terminal:
                break
            if self._paused:
                await workflow.wait_condition(lambda: not self._paused or self._terminal)
                continue

            woke_on_signal = bool(
                self._pending_events or self._pending_instructions or self._wake_now
            )
            if not woke_on_signal:
                await self._act("lifecycle", "scheduled wake-up", {})  # timer elapsed
                await self._run_agent("scheduled")
            else:
                await self._handle_signals()
                if self._wake_now and not self._terminal:
                    self._wake_now = False
                    await self._run_agent("signal")

            self._check_max_age()

            rollover = self._wake_config().get("continue_as_new_every", CONTINUE_AS_NEW_EVERY)
            if not self._terminal and self._events_processed >= rollover:
                await self._compact(force=True)
                workflow.continue_as_new(self._carry())

        await self._finish()
        return {"status": self._status, "reason": self._terminate_reason}

    # -------------------------------------------------------------- signals
    @workflow.signal
    def submit_event(self, event: dict[str, Any]) -> None:
        self._pending_events.append(
            Event(type=event["type"], payload=event.get("payload", {}))
        )

    @workflow.signal
    def add_instruction(self, text: str) -> None:
        self._pending_instructions.append(text)

    @workflow.signal
    def pause(self) -> None:
        self._paused = True
        self._status = "paused"

    @workflow.signal
    def resume(self) -> None:
        self._paused = False
        self._status = "running"

    @workflow.signal
    def interrupt(self) -> None:
        self._wake_now = True  # force an inference on the next turn

    @workflow.signal
    def terminate_run(self, reason: str) -> None:
        self._terminal = True
        self._terminate_reason = reason or "manual"

    # --------------------------------------------------------------- query
    @workflow.query
    def get_state(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "paused": self._paused,
            "terminal": self._terminal,
            "memory_summary": self._memory_summary,
            "next_wakeup": self._next_wakeup_iso,
            "instructions": self._instructions,
            "events_processed": self._events_processed,
            "timeline_tail": [t.__dict__ for t in self._timeline_tail],
        }

    # ------------------------------------------------------------- helpers
    def _load(self, arg: WorkflowInput) -> bool:
        self._input = arg
        if arg.is_resume:
            self._memory_summary = arg.resume_memory
            self._next_wakeup_iso = arg.resume_next_wakeup_iso
            self._instructions = list(arg.resume_instructions)
            self._events_processed = arg.resume_events_processed
            self._started_at_iso = arg.resume_started_at_iso or workflow.now().isoformat()
            return False
        self._started_at_iso = workflow.now().isoformat()
        return True

    async def _sleep(self) -> None:
        timeout = self._sleep_timeout()
        self._status = "paused" if self._paused else "running"
        await self._sync("sleeping")
        # Only log a sleep when we're actually resting, not when a signal is already waiting.
        resting = not (self._paused or self._pending_events or self._pending_instructions or self._wake_now)
        if resting and timeout.total_seconds() > 2:
            await self._act(
                "sleep", f"sleeping until {self._next_wakeup_iso or 'next signal'}",
                {"seconds": round(timeout.total_seconds())},
            )
        try:
            await workflow.wait_condition(
                lambda: self._wake_now
                or self._terminal
                or bool(self._pending_events)
                or bool(self._pending_instructions)
                or self._paused,
                timeout=timeout,
            )
        except TimeoutError:
            pass  # scheduled wake-up

    def _sleep_timeout(self) -> timedelta:
        cap = timedelta(seconds=self._wake_config().get("max_sleep_s", DEFAULT_MAX_SLEEP_S))
        if self._next_wakeup_iso:
            delta = datetime.fromisoformat(self._next_wakeup_iso) - workflow.now()
            if delta.total_seconds() <= 0:
                return timedelta(seconds=1)
            return min(delta, cap)
        return cap

    async def _handle_signals(self) -> None:
        events, self._pending_events = self._pending_events, []
        for ev in events:
            await self._act("event", ev.type, {"type": ev.type, **ev.payload})
            self._timeline_tail.append(
                TimelineItem("event", f"{ev.type} {ev.payload or ''}".strip())
            )
            self._events_processed += 1

            if ev.type in TERMINAL_EVENTS:
                self._terminal = True
                self._terminate_reason = f"terminal_event:{ev.type}"

            important, reason = await self._classify(ev)
            await self._act(
                "wake_decision",
                f"{'WAKE' if important else 'SLEEP'}: {ev.type}",
                {"important": important, "reason": reason},
            )
            if important:
                self._wake_now = True

        if self._pending_instructions:
            new, self._pending_instructions = self._pending_instructions, []
            for text in new:
                self._instructions.append(text)
                await self._act("instruction", "added instruction", {"text": text})
            self._wake_now = True

    async def _classify(self, ev: Event) -> tuple[bool, str]:
        """Rule policy for known events; LLM only for unknown ones."""
        aggr = self._wake_config().get("aggressiveness", "medium")
        critical = {"payment_failed", "shipment_delayed", "cancelled", "delivered"}
        routine = {"order_created", "payment_confirmed", "shipment_created"}

        if ev.type in critical:
            return True, "known-critical event"
        if ev.type in routine:
            if aggr == "high":
                return True, "high aggressiveness wakes on routine progress"
            return False, "routine progress, staying asleep"

        important = await workflow.execute_activity(
            "classify_unknown_event",
            args=[ev.type, ev.payload, aggr],
            result_type=bool,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_RETRY,
        )
        return bool(important), "unknown event, classified by LLM"

    async def _run_agent(self, trigger: str) -> None:
        ctx = AgentContext(
            run_id=self._input.run_id,
            order_id=self._input.order_id,
            trigger=trigger,
            base_instruction=self._input.supervisor.base_instruction,
            instructions=self._instructions,
            enabled_actions=self._input.supervisor.enabled_actions,
            memory_summary=self._memory_summary,
            timeline_tail=self._timeline_tail,
            order_context=self._input.order_context,
            wake_config=self._wake_config(),
            model=self._input.supervisor.model,
            now_iso=workflow.now().isoformat(),
        )
        decision: AgentDecision = await workflow.execute_activity(
            "agent_inference",
            ctx,
            result_type=AgentDecision,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=_RETRY,
        )
        await self._apply(decision, trigger)

    async def _apply(self, decision: AgentDecision, trigger: str) -> None:
        if decision.reasoning:
            self._timeline_tail.append(TimelineItem("reasoning", decision.reasoning))
            await self._act("reasoning", f"reasoning ({trigger})", {"text": decision.reasoning})
        for a in decision.actions:
            self._timeline_tail.append(TimelineItem("action", f"{a.name}: {a.result}"))
        if decision.new_memory:
            self._memory_summary = decision.new_memory
            await self._act("memory_update", "memory refreshed", {"summary": decision.new_memory})

        # Adopt the agent's proposed wake-up; the workflow still caps it in _sleep_timeout.
        # If the agent proposed nothing, fall back to the supervisor's default interval so
        # scheduled wake-ups keep happening regardless of the model's behavior.
        if decision.next_wakeup_iso:
            self._next_wakeup_iso = decision.next_wakeup_iso
        elif decision.sleep_seconds is not None:
            target = workflow.now() + timedelta(seconds=max(1, decision.sleep_seconds))
            self._next_wakeup_iso = target.isoformat()
        else:
            interval = self._wake_config().get("default_interval_s", DEFAULT_INTERVAL_S)
            self._next_wakeup_iso = (workflow.now() + timedelta(seconds=interval)).isoformat()

        if decision.recommend_completion:
            await self._act(
                "lifecycle", "agent recommends completion",
                {"note": "non-binding; workflow rules decide"},
            )
        if decision.final_output:
            await self._act("final", "final report", decision.final_output)
            await workflow.execute_activity(
                "save_final_output",
                args=[self._input.run_id, decision.final_output],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=_RETRY,
            )

        await self._compact(force=False)
        await self._sync("awake")

    async def _finish(self) -> None:
        await self._run_agent("final")  # summary, learnings, feedback
        self._status = "terminated" if self._terminate_reason == "manual" else "completed"
        await self._act("lifecycle", f"run {self._status}", {"reason": self._terminate_reason})
        await workflow.execute_activity(
            "finalize_run",
            args=[self._input.run_id, self._status],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_RETRY,
        )

    async def _compact(self, force: bool) -> None:
        if not self._timeline_tail:
            return
        if not force and len(self._timeline_tail) <= TAIL_LIMIT:
            return
        keep = 4
        old = self._timeline_tail if force else self._timeline_tail[:-keep]
        if not old:
            return
        self._memory_summary = await workflow.execute_activity(
            "compact_memory",
            args=[self._input.run_id, self._memory_summary, [t.__dict__ for t in old]],
            result_type=str,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=_RETRY,
        )
        self._timeline_tail = [] if force else self._timeline_tail[-keep:]

    def _check_max_age(self) -> None:
        max_age = self._wake_config().get("max_age_s")
        if not max_age:
            return
        started = datetime.fromisoformat(self._started_at_iso)
        if (workflow.now() - started).total_seconds() >= max_age:
            self._terminal = True
            self._terminate_reason = "max_age"

    def _carry(self) -> WorkflowInput:
        base = self._input
        return WorkflowInput(
            run_id=base.run_id,
            order_id=base.order_id,
            supervisor=base.supervisor,
            order_context=base.order_context,
            is_resume=True,
            resume_memory=self._memory_summary,
            resume_next_wakeup_iso=self._next_wakeup_iso,
            resume_instructions=self._instructions,
            resume_events_processed=0,
            resume_started_at_iso=self._started_at_iso,
        )

    def _wake_config(self) -> dict[str, Any]:
        return self._input.supervisor.wake_config or {}

    # --- activity shims (all IO lives in activities) ----------------------
    async def _act(self, type_: str, title: str, payload: dict[str, Any]) -> None:
        await workflow.execute_activity(
            "log_activity",
            args=[self._input.run_id, type_, title, payload],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_RETRY,
        )

    async def _sync(self, sleep_state: str) -> None:
        await workflow.execute_activity(
            "sync_run_state",
            args=[self._input.run_id, self._status, self._next_wakeup_iso, sleep_state,
                  self._memory_summary],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_RETRY,
        )
