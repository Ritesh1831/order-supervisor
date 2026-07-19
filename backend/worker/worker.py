import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app import db
from app.config import TEMPORAL_HOST, TEMPORAL_NAMESPACE, TEMPORAL_TASK_QUEUE
from worker import activities
from worker.workflows import OrderSupervisorWorkflow

ACTIVITIES = [
    activities.log_activity,
    activities.sync_run_state,
    activities.agent_inference,
    activities.classify_unknown_event,
    activities.compact_memory,
    activities.save_final_output,
    activities.finalize_run,
]


async def main() -> None:
    await db.init_schema()
    client = await Client.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)
    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[OrderSupervisorWorkflow],
        activities=ACTIVITIES,
    )
    print(f"worker up on task queue '{TEMPORAL_TASK_QUEUE}'")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
