import json
import os
from typing import Any, Optional

import asyncpg

from app.config import DATABASE_URL

_pool: Optional[asyncpg.Pool] = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    # Let us pass/receive Python dicts and lists for jsonb columns directly.
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10, init=_init_conn)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def init_schema() -> None:
    path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(path) as f:
        ddl = f.read()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(ddl)


# --- activity log ---------------------------------------------------------

async def add_activity(
    run_id: str, type_: str, title: str, payload: dict[str, Any] | None = None
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO activities (run_id, type, title, payload) VALUES ($1,$2,$3,$4)",
            run_id,
            type_,
            title,
            payload or {},
        )


async def list_activities(run_id: str) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, type, title, payload, created_at FROM activities "
            "WHERE run_id=$1 ORDER BY id",
            run_id,
        )
    return [dict(r) for r in rows]


# --- runs -----------------------------------------------------------------

async def create_run(
    run_id: str,
    order_id: str,
    supervisor_id: str,
    workflow_id: str,
    order_context: dict[str, Any],
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO runs (id, order_id, supervisor_id, workflow_id, order_context) "
            "VALUES ($1,$2,$3,$4,$5) ON CONFLICT (id) DO NOTHING",
            run_id,
            order_id,
            supervisor_id,
            workflow_id,
            order_context,
        )


async def update_run(run_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols = list(fields.keys())
    sets = ", ".join(f"{c}=${i+2}" for i, c in enumerate(cols))
    vals = [fields[c] for c in cols]
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE runs SET {sets}, updated_at=now() WHERE id=$1", run_id, *vals
        )


async def get_run(run_id: str) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM runs WHERE id=$1", run_id)
    return dict(row) if row else None


async def list_runs() -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM runs ORDER BY created_at DESC")
    return [dict(r) for r in rows]


# --- supervisors ----------------------------------------------------------

async def upsert_supervisor(s: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO supervisors (id, name, base_instruction, enabled_actions, wake_config, model) "
            "VALUES ($1,$2,$3,$4,$5,$6) "
            "ON CONFLICT (id) DO UPDATE SET name=$2, base_instruction=$3, "
            "enabled_actions=$4, wake_config=$5, model=$6",
            s["id"],
            s["name"],
            s["base_instruction"],
            s["enabled_actions"],
            s["wake_config"],
            s["model"],
        )


async def get_supervisor(sid: str) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM supervisors WHERE id=$1", sid)
    return dict(row) if row else None


async def list_supervisors() -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM supervisors ORDER BY created_at")
    return [dict(r) for r in rows]
