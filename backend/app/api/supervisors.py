import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import db

router = APIRouter(prefix="/api/supervisors", tags=["supervisors"])


class SupervisorIn(BaseModel):
    name: str
    base_instruction: str
    enabled_actions: list[str]
    wake_config: dict[str, Any] = Field(default_factory=dict)
    model: str = "llama-3.3-70b-versatile"


@router.get("")
async def list_supervisors():
    return await db.list_supervisors()


@router.post("")
async def create_supervisor(body: SupervisorIn):
    sid = str(uuid.uuid4())[:8]
    s = {"id": sid, **body.model_dump()}
    await db.upsert_supervisor(s)
    return await db.get_supervisor(sid)


@router.get("/{sid}")
async def get_supervisor(sid: str):
    s = await db.get_supervisor(sid)
    if not s:
        raise HTTPException(404, "supervisor not found")
    return s
