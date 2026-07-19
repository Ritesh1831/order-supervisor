CREATE TABLE IF NOT EXISTS supervisors (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    base_instruction TEXT NOT NULL,
    enabled_actions JSONB NOT NULL DEFAULT '[]',
    wake_config     JSONB NOT NULL DEFAULT '{}',
    model           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
    id             TEXT PRIMARY KEY,
    order_id       TEXT NOT NULL,
    supervisor_id  TEXT NOT NULL REFERENCES supervisors(id),
    workflow_id    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'running',
    memory_summary TEXT NOT NULL DEFAULT '',
    next_wakeup    TIMESTAMPTZ,
    sleep_state    TEXT NOT NULL DEFAULT 'awake',
    order_context  JSONB NOT NULL DEFAULT '{}',
    final_output   JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Single unified log for everything that happens in a run.
CREATE TABLE IF NOT EXISTS activities (
    id         BIGSERIAL PRIMARY KEY,
    run_id     TEXT NOT NULL REFERENCES runs(id),
    type       TEXT NOT NULL,   -- event|wake_decision|sleep|action|instruction|reasoning|memory_update|lifecycle|final
    title      TEXT NOT NULL,
    payload    JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS activities_run_idx ON activities(run_id, id);
