import asyncio

import pytest

from curateur.workflow.work_queue import WorkQueueManager, WorkItem, Priority


@pytest.mark.unit
@pytest.mark.asyncio
async def test_work_queue_respects_priority_and_retries():
    manager = WorkQueueManager(max_retries=2)

    manager.add_work({"filename": "low"}, action="full", priority=Priority.LOW)
    manager.add_work({"filename": "high"}, action="full", priority=Priority.HIGH)

    first = await manager.get_work_async()
    assert first.rom_info["filename"] == "high"

    # retry high item once (still under max)
    manager.retry_failed(first, error="oops")
    retry_item = await manager.get_work_async()
    assert retry_item.retry_count == 1
    assert retry_item.priority == Priority.HIGH

    # exceed retries
    manager.retry_failed(retry_item, error="fail again")
    assert len(manager.failed) == 1
    assert manager.failed[0]["error"] == "fail again"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mark_processed_and_complete():
    manager = WorkQueueManager()
    manager.add_work({"filename": "one"}, action="full")
    item = await manager.get_work_async()
    await manager.mark_processed(item)
    assert manager.processed_count == 1

    assert manager.is_empty() is True
    manager.mark_system_complete()
    assert await manager.get_work_async() is None

    stats = manager.get_stats()
    assert stats["processed"] == 1
