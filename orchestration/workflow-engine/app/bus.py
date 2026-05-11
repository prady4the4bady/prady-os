"""Redis Streams message bus for inter-agent communication."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

STREAM_PREFIX = "kryos:stream:"
CONDUCTOR_RESULTS_STREAM = f"{STREAM_PREFIX}conductor:results"
TASKS_INBOX_STREAM = f"{STREAM_PREFIX}tasks:inbox"
_CONNECT_FIRST_MESSAGE = "Call connect() first"


def agent_stream(agent_type: str) -> str:
    """Return the Redis stream name for a given agent type."""
    return f"{STREAM_PREFIX}agent:{agent_type}"


def _encode(fields: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in fields.items():
        if isinstance(v, (dict, list)):
            out[k] = json.dumps(v)
        elif v is None:
            out[k] = "null"
        else:
            out[k] = str(v)
    return out


def _decode(fields: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in fields.items():
        try:
            out[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            out[k] = v
    return out


class MessageBus:
    """Thin wrapper around Redis Streams for publishing and consuming messages."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        await asyncio.sleep(0)
        logger.info("MessageBus connected to %s", self._redis_url)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            logger.info("MessageBus disconnected")

    async def publish(self, stream: str, message: Dict[str, Any]) -> str:
        """Append a message to *stream*. Returns the Redis message ID."""
        assert self._client, _CONNECT_FIRST_MESSAGE
        msg_id = await self._client.xadd(stream, _encode(message))
        logger.debug("Published %s → %s", msg_id, stream)
        return msg_id

    async def read_new(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 10,
        block_ms: Optional[int] = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Read undelivered messages from a consumer group (XREADGROUP)."""
        assert self._client, _CONNECT_FIRST_MESSAGE
        try:
            await self._client.xgroup_create(
                stream, consumer_group, id="0", mkstream=True
            )
        except aioredis.ResponseError:
            pass  # group already exists

        entries = await self._client.xreadgroup(
            groupname=consumer_group,
            consumername=consumer_name,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )
        if not entries:
            return []

        results: List[Tuple[str, Dict[str, Any]]] = []
        for _, messages in entries:
            for msg_id, raw_fields in messages:
                results.append((msg_id, _decode(raw_fields)))
        return results

    async def ack(self, stream: str, consumer_group: str, msg_id: str) -> None:
        """Acknowledge a processed message (XACK)."""
        assert self._client, _CONNECT_FIRST_MESSAGE
        await self._client.xack(stream, consumer_group, msg_id)

    async def ping(self) -> bool:
        if not self._client:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    @property
    def client(self) -> Optional[aioredis.Redis]:
        return self._client
