"""Drive a realistic order lifecycle into a run via the API.

Usage:
    uv run python scripts/simulate.py <run_id> [--fast]
"""
import asyncio
import sys

import httpx

API = "http://localhost:8000"

# (event_type, payload, seconds_to_wait_after)
SCRIPT = [
    ("payment_confirmed", {"amount": 49.0}, 4),
    ("shipment_created", {"carrier": "UPS", "eta_days": 3}, 4),
    ("shipment_delayed", {"reason": "weather", "extra_days": 2}, 6),
    ("delivered", {}, 0),
]


async def main() -> None:
    if len(sys.argv) < 2:
        print("usage: simulate.py <run_id> [--fast]")
        raise SystemExit(1)
    run_id = sys.argv[1]
    fast = "--fast" in sys.argv

    async with httpx.AsyncClient(timeout=30) as c:
        for etype, payload, wait in SCRIPT:
            r = await c.post(f"{API}/api/runs/{run_id}/events", json={"type": etype, "payload": payload})
            r.raise_for_status()
            print(f"-> sent {etype} {payload}")
            await asyncio.sleep(1 if fast else wait)
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
