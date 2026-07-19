# Notes on the approach

How I built the Order Supervisor and why it's put together the way it is. The README covers how to
run it; this is the thinking behind it. The brief said the things that matter most are the system
design, the Temporal usage, the agent orchestration, and whether it actually works end to end, so
that's roughly how I've organised these notes.

## Scope, and how I built it

One supervisor that follows a single order for its whole life: it reacts to events, keeps a memory,
acts through tools, sleeps when there's nothing to do, wakes on a schedule or when something
important lands, and writes a summary at the end. The e-commerce parts are mocked on purpose — the
interesting problem is the long-running workflow and the agent on top of it, not order management.
I kept the surface small so those two parts could stay clean.

I built it bottom-up: infra first (Temporal + Postgres), then the workflow "spine" with a *fake*
agent so I could watch the triggers and timers behave in the Temporal UI before any model was
involved, then the real Groq agent, then events and lifecycle, then memory compaction and
`continue_as_new`, then the UI and docs. Getting the Temporal behaviour solid before adding the LLM
is what saved me the most debugging.

## System design

The rule I stuck to everywhere: **the workflow owns control, activities own side effects.** The
workflow is deterministic — it holds the timers, the sleep/wake loop, and every "when" decision.
Anything non-deterministic (model calls, DB writes) is an activity. So the layering is Next UI →
FastAPI → Temporal client → the workflow → activities → Postgres. The UI reads run state from
Postgres because it's durable and easy to query, and only goes through the API to send signals.

Data is deliberately thin — three tables. `supervisors`, `runs`, and a single `activities` log that
every event, decision, action, reasoning step, memory update and final report writes to. The UI
timeline is literally that log in order: no separate messages table, no derived state to keep in
sync.

The agent never touches control directly. It returns an `AgentDecision` — its reasoning, the
actions it took, an updated memory summary, a proposed next wake-up, and whether it recommends
finishing — and the workflow applies the parts it's allowed to. That split is what keeps replay
safe and makes it obvious who's in charge of the clock.

## Temporal usage

One workflow run per order, keyed `order-<id>`, so starting the same order twice is a no-op instead
of a duplicate — the "one workflow per order" requirement just falls out of the id.

The sleep/wake loop is a single `wait_condition` with a timeout. The workflow sleeps until either
its next scheduled wake-up fires (the timeout) or a signal flips the condition (an event, an
instruction, an interrupt). That one construct covers all three inference triggers the brief asked
for — start, signal, scheduled — and it's genuinely idle in between, not polling.

Signals in: `submit_event`, `add_instruction`, `pause`, `resume`, `interrupt`, `terminate`. A
`get_state` query exposes a live snapshot for anyone who wants it. Activities carry retry policies,
and I keep the workflow file import-light so it loads cleanly inside the Temporal sandbox.

Two things specifically for long-running modelling: a `max_sleep_s` cap so a run never goes dark
even if the agent over-sleeps, and `continue_as_new` once a run has processed enough events, so its
history stays bounded. And completion is a workflow rule, never the agent's call — a terminal event
(`delivered`/`cancelled`), a manual terminate, or hitting max age. The agent can *recommend*
finishing; the workflow decides. That was an explicit ask, and it's easy to get wrong by just
letting the model end the run.

## Agent orchestration

The agent is a bounded tool-calling loop on Groq, and the tools come in two families, which I think
is the cleanest way to model it. **Business actions** (send customer message, internal note,
escalate, mark for review, request human review) write activity rows. **Control tools** (sleep,
schedule next wake-up, update memory, recommend completion, submit final report) fold into the
`AgentDecision` for the workflow to enforce. Business tools *do* things; control tools *ask the
workflow* to do things.

In front of the agent is a cheap classifier so the expensive loop doesn't fire on every event.
Known events use a rule — a payment failure or shipment delay wakes it, routine progress doesn't,
shifted by the supervisor's aggressiveness setting. Unknown event types get a one-line wake/sleep
judgement from the model and default to escalating. When the classifier says "not important", the
event is logged and the run sleeps on. That gate is where the sleep/wake behaviour actually lives.

Memory is a rolling summary the agent maintains, with older timeline entries compacted into it once
there are enough, so the context it reasons over stays small. Per-run instructions ("prioritise
speed", "don't contact the customer without review") get injected into that context and the agent
follows them. The final step is its own trigger and produces a structured report — summary, key
actions, learnings, recommendations.

## Working end to end

It behaves like a product, not a script. You create or pick a supervisor config, start a run, and
watch the timeline update live — events, the wake/sleep decision for each, sleeps, reasoning,
actions — while injecting events, adding instructions, and pausing/interrupting/terminating, with
the same run visible in the Temporal UI. There's a simulate script and an event panel (including a
custom event type to exercise the classifier), and two integration tests that drive the whole
workflow against a real local Temporal server using a fake model, so they run with no key and no
Docker.

The LLM sits behind a one-file provider seam. The only reason it's abstracted at all is so those
tests can drop in a deterministic fake — otherwise it's just Groq.

## Trade-offs and what I left out

- No auth, no real integrations, no multi-tenant — out of scope per the brief.
- One activity runs the whole agent loop and writes the action rows, rather than each tool being
  its own Temporal activity. Cleaner code, slightly less granular history. For a POC I'd make that
  trade again.
- `log_activity` isn't idempotent, so a rare activity retry could double-write a row.
- Run analytics are computed in the browser from the activity log instead of a dedicated endpoint.

If I kept going I'd let the agent tune the classifier's aggressiveness over the life of a run, give
each business tool its own activity so the Temporal history reads as a clean audit trail, and add a
small analytics endpoint.
