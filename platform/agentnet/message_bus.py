"""AgentNet message bus — signed message format and verification."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .identity import generate_identity, verify_message

logger = logging.getLogger(__name__)

MESSAGES_LOG = Path(__file__).resolve().parent / "logs" / "messages.jsonl"


def _append_log(record: Dict[str, Any]) -> None:
    MESSAGES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with MESSAGES_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


class SignedMessage:
    """Represents a signed inter-agent message."""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        payload: Dict[str, Any],
        signature: str,
        timestamp: float,
    ) -> None:
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.payload = payload
        self.signature = signature
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "payload": self.payload,
            "signature": self.signature,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignedMessage":
        return cls(
            from_agent=data["from"],
            to_agent=data["to"],
            payload=data["payload"],
            signature=data["signature"],
            timestamp=data["timestamp"],
        )


class MessageBus:
    """Signs outbound messages and verifies inbound messages."""

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def create_message(
        self,
        from_agent: str,
        to_agent: str,
        payload: Dict[str, Any],
    ) -> SignedMessage:
        """Create and sign a message from *from_agent* to *to_agent*."""
        timestamp = time.time()
        canonical = json.dumps({"from": from_agent, "to": to_agent, "payload": payload, "timestamp": timestamp}, sort_keys=True)
        identity = generate_identity(from_agent)
        signature = identity.sign(canonical.encode())

        msg = SignedMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            payload=payload,
            signature=signature,
            timestamp=timestamp,
        )
        _append_log({"direction": "outbound", **msg.to_dict()})
        return msg

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    def receive_message(
        self,
        raw: Dict[str, Any],
        sender_pub_key_pem: Optional[str] = None,
    ) -> Optional[SignedMessage]:
        """Verify and return a SignedMessage, or None if invalid."""
        try:
            msg = SignedMessage.from_dict(raw)
        except (KeyError, TypeError) as exc:
            logger.warning("MessageBus: malformed message: %s", exc)
            return None

        if sender_pub_key_pem is not None:
            canonical = json.dumps(
                {"from": msg.from_agent, "to": msg.to_agent, "payload": msg.payload, "timestamp": msg.timestamp},
                sort_keys=True,
            )
            if not verify_message(sender_pub_key_pem, canonical.encode(), msg.signature):
                logger.warning("MessageBus: invalid signature from %s", msg.from_agent)
                _append_log({"direction": "rejected", "reason": "invalid_signature", **msg.to_dict()})
                return None

        _append_log({"direction": "inbound", **msg.to_dict()})
        return msg


# Module-level singleton
bus = MessageBus()
