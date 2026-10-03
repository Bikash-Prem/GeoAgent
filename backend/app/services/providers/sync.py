"""Run the async provider adapters from synchronous code (FastAPI sync endpoints run in worker threads)."""
import asyncio
import concurrent.futures


def run_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)          # normal case: a worker thread with no event loop
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:  # called from inside an event loop
        return pool.submit(asyncio.run, coro).result()
