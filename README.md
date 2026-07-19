# Order Supervisor

An AI "supervisor" that watches a single order from the moment it's placed until it's
delivered or cancelled. Every order gets its own long-running Temporal workflow. Events arrive
as they happen, and the agent decides whether to step in, do nothing, or check back later. When
the order reaches the end of its life it writes up what happened and what it learned.

The e-commerce side is all mocked on purpose. The parts I actually cared about are the
long-running workflow, the sleep/wake behaviour, and how the agent is wired into Temporal.

## Architecture note

The short version of how it's put together:

```
                  browser
                     │
                     ▼
              ┌─────────────┐        start · signal · query · terminate
              │  Next.js UI │ ───────────────────────────────────────────┐
              └──────┬──────┘                                             │
                     │ /api (proxied to FastAPI)                          ▼
                     ▼                                    ┌────────────────────────────┐
              ┌─────────────┐                             │ Temporal                   │
              │   FastAPI   │ ─── start/signal ─────────► │ OrderSupervisor workflow   │
              └──────┬──────┘                             │ (one running per order)    │
                     │                                    └──────────────┬─────────────┘
        reads run    │                                                   │ activities (LLM + DB)
        state from   ▼                                                   ▼
              ┌─────────────┐   ◄──── activity log ────   agent inference · wake/sleep
              │ PostgreSQL  │                             classifier · memory compaction
              └─────────────┘                             · business tools
```

A few decisions that shaped the design:

- **One workflow per order.** The workflow id is `order-<id>`, so starting the same order twice
  is a no-op rather than a duplicate.
- **The workflow owns the clock, the agent just advises.** Timers, sleeping, waking, and deciding
  when a run is finished all live in the workflow (which has to be deterministic for Temporal to
  replay it). Anything that touches the outside world — the LLM calls, the database — runs in
  activities. The agent proposes a next wake-up or that the run should end; the workflow decides.
- **Not every event wakes the agent.** Each incoming event first hits a small classifier. Known
  events use a plain rule (a payment failure or a shipment delay is worth waking up for; routine
  progress isn't). Anything unrecognised gets a quick yes/no from the model. If the answer is
  "not important", the event is logged and the run goes back to sleep until its next scheduled
  check — the expensive agent loop never runs.
- **Completion is a workflow rule, not the agent's call.** A run ends when a terminal event
  arrives (`delivered`/`cancelled`), when it's terminated from the UI, or when it hits a max age.

Memory is a rolling summary the agent keeps up to date, and older timeline entries get folded into
it once there are enough of them. For very long histories the workflow uses `continue_as_new` so
its event history stays bounded.

On storage: everything a run does — events, wake/sleep decisions, actions, reasoning, memory
updates, the final report — lands in one `activities` table, and that's exactly what the timeline
in the UI reads. Supervisors and runs have their own tables. There's no separate messages table;
the activity log *is* the timeline. The three inference triggers (start, an important signal, a
scheduled wake-up) are the only times the main agent runs.

## Screenshots

The app — a run's timeline, memory, and controls:

<!-- ![App](docs/screenshots/app.png) -->
_(screenshot coming)_

Temporal UI (one workflow per order, signals, timers between wake-ups):

<!-- ![Temporal UI](docs/screenshots/temporal.png) -->
_(screenshot coming)_

FastAPI docs (`/docs`):

<!-- ![Swagger](docs/screenshots/swagger.png) -->
_(screenshot coming)_

## Stack

- Next.js (App Router) + Tailwind
- FastAPI
- Temporal (Python SDK)
- PostgreSQL
- Groq (`llama-3.3-70b-versatile`) for the agent and the unknown-event classifier

## Running it locally

You'll need Docker + Compose, [uv](https://docs.astral.sh/uv/), Node 18+, and a free Groq API key
(https://console.groq.com/keys).

```bash
cp .env.example .env        # then put your GROQ_API_KEY in it
docker compose up -d        # Temporal + Postgres (Temporal UI on :8233)
```

Then three processes, each in its own terminal, from the repo:

```bash
cd backend && uv sync
uv run python -m worker.worker                     # Temporal worker
uv run uvicorn app.main:app --reload --port 8000   # API (creates tables + seeds templates)

cd frontend && npm install && npm run dev          # UI on http://localhost:3000
```

Open http://localhost:3000, pick a supervisor, and start a run. To push a full lifecycle at it:

```bash
cd backend
uv run python scripts/simulate.py order-ORD-XXXXXX   # your run id
```

The timeline shows the whole rhythm — events, the wake/sleep decision for each one, the agent's
reasoning, sleeps, actions, and the final report. The template wake intervals are short (45–120s)
on purpose so you don't have to wait around to see a scheduled wake-up.

From a run you can inject events (pick a built-in one, or "Custom (With LLM)" to fire an unknown
type and watch the model classify it), add instructions to the live run, pause / interrupt /
terminate it, and download the full timeline as JSON.

## Tests

```bash
cd backend
uv run --extra test pytest -v
```

Two integration tests run the workflow against Temporal's local test server (downloaded the first
time) with an in-memory DB and a fake model, so they need neither Docker nor a key. They cover the
three triggers, the classifier gate, completion + final report, and `continue_as_new`.

## Layout

```
backend/
  app/      FastAPI, DB access, config, supervisor templates
  worker/   Temporal workflow + activities + the agent (Groq provider, tools, prompts)
  scripts/  seed.py, simulate.py
  tests/
frontend/   Next.js App Router UI
docker-compose.yml        # Temporal + Postgres for local dev
```
