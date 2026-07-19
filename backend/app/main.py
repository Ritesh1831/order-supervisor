from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.api import runs, supervisors
from app.supervisors.templates import TEMPLATES


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_schema()
    for t in TEMPLATES:  # seed hardcoded templates if missing
        if not await db.get_supervisor(t["id"]):
            await db.upsert_supervisor(t)
    yield
    await db.close_pool()


app = FastAPI(title="Order Supervisor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(supervisors.router)
app.include_router(runs.router)


@app.get("/api/health")
async def health():
    return {"ok": True}
