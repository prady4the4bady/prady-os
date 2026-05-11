"""Tests for Redis-backed task queue."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    return r


@pytest.mark.asyncio
async def test_push_task(mock_redis: AsyncMock) -> None:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from task_queue import push_task, TaskPushRequest
    mock_redis.set = AsyncMock()
    mock_redis.zadd = AsyncMock()
    with patch("task_queue._redis", return_value=mock_redis):
        result = await push_task(TaskPushRequest(goal="test goal"))
    assert result["status"] == "pending"
    assert result["task_id"].startswith("task-")


@pytest.mark.asyncio
async def test_get_next_task_empty(mock_redis: AsyncMock) -> None:
    from task_queue import get_next_task
    mock_redis.zpopmin = AsyncMock(return_value=[])
    with patch("task_queue._redis", return_value=mock_redis):
        result = await get_next_task()
    assert result["task"] is None


@pytest.mark.asyncio
async def test_list_tasks_empty(mock_redis: AsyncMock) -> None:
    from task_queue import list_tasks
    mock_redis.zrange = AsyncMock(return_value=[])
    with patch("task_queue._redis", return_value=mock_redis):
        result = await list_tasks()
    assert result["tasks"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_delete_task_not_found(mock_redis: AsyncMock) -> None:
    from task_queue import delete_task
    from fastapi import HTTPException
    mock_redis.zrem = AsyncMock(return_value=0)
    mock_redis.delete = AsyncMock()
    with patch("task_queue._redis", return_value=mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            await delete_task("nonexistent")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_success(mock_redis: AsyncMock) -> None:
    from task_queue import delete_task
    mock_redis.zrem = AsyncMock(return_value=1)
    mock_redis.delete = AsyncMock()
    with patch("task_queue._redis", return_value=mock_redis):
        result = await delete_task("task-abc")
    assert result["deleted"] is True
