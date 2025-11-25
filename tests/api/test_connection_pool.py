import pytest

from curateur.api.connection_pool import ConnectionPoolManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_pool_create_and_close():
    manager = ConnectionPoolManager(config={"api": {"request_timeout": 5}})
    client = await manager.get_client(max_connections=2)
    assert client is not None
    stats = manager.get_stats()
    assert stats["client_active"] is True
    assert stats["config_timeout"] == 5

    await manager.close_client()
    assert manager.client is None
