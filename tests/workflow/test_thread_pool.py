import asyncio

import pytest

from curateur.workflow.thread_pool import ThreadPoolManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_thread_pool_initialize_and_submit(monkeypatch):
    manager = ThreadPoolManager(config={"runtime": {}})
    manager.initialize_pools(api_provided_limits={"maxthreads": 2})
    assert manager.max_concurrent == 2
    assert manager.semaphore._value == 2  # type: ignore[attr-defined]

    async def rom_processor(rom, cb):
        await asyncio.sleep(0.01)
        return {"result": rom}

    roms = [{"id": 1}, {"id": 2}]
    results = []
    async for rom, result in manager.submit_rom_batch(rom_processor, roms):
        results.append(result)

    assert len(results) == 2
    assert results[0]["result"] in roms


@pytest.mark.unit
@pytest.mark.asyncio
async def test_thread_pool_stop_workers(monkeypatch):
    manager = ThreadPoolManager(config={"runtime": {}})
    manager.initialize_pools({"maxthreads": 1})

    # Spawn a long-running fake worker
    manager._worker_tasks = [asyncio.create_task(asyncio.sleep(0.1))]
    manager._workers_stopped = False
    await manager.stop_workers()
    assert manager._workers_stopped is True
