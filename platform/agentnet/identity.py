"""AgentIdentity — Ed25519 keypair management for inter-agent message signing."""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_KEYS_ROOT = Path(__file__).resolve().parent / "keys"


def _keys_root() -> Path:
    """Return key storage directory, respecting AGENTNET_KEY_DIR env var."""
    env = os.environ.get("AGENTNET_KEY_DIR")
    return Path(env) if env else _DEFAULT_KEYS_ROOT


def _priv_path(agent_id: str) -> Path:
    return _keys_root() / f"{agent_id}.priv"


def _pub_path(agent_id: str) -> Path:
    return _keys_root() / f"{agent_id}.pub"


class AgentIdentity:
    """Holds the Ed25519 keypair for a single agent."""

    def __init__(self, agent_id: str) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )

        self.agent_id = agent_id
        self._private_key: Ed25519PrivateKey
        self._public_key: Ed25519PublicKey

        priv = _priv_path(agent_id)
        pub = _pub_path(agent_id)
        if priv.exists() and pub.exists():
            self._load(priv, pub)
        else:
            self._generate_and_save(agent_id)

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    def _generate_and_save(self, agent_id: str) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )

        KEYS_ROOT = _keys_root()
        KEYS_ROOT.mkdir(parents=True, exist_ok=True)
        priv_key = Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()

        priv_bytes = priv_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        pub_bytes = pub_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)

        priv_path = _priv_path(agent_id)
        pub_path = _pub_path(agent_id)

        priv_path.write_bytes(priv_bytes)
        priv_path.chmod(0o600)
        pub_path.write_bytes(pub_bytes)

        self._private_key = priv_key
        self._public_key = pub_key
        logger.info("AgentIdentity: generated keypair for %s", agent_id)

    def _load(self, priv_path: Path, pub_path: Path) -> None:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        priv_bytes = priv_path.read_bytes()
        pub_bytes = pub_path.read_bytes()

        priv_key = load_pem_private_key(priv_bytes, password=None)
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        self._private_key = priv_key  # type: ignore[assignment]
        self._public_key = load_pem_public_key(pub_bytes)  # type: ignore[assignment]

    @property
    def public_key_pem(self) -> str:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        return self._public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ).decode()

    @property
    def private_key_pem(self) -> str:
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
        )

        return self._private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode()

    def sign(self, payload: bytes) -> str:
        """Sign *payload* and return base64-encoded signature."""
        sig = self._private_key.sign(payload)
        return base64.b64encode(sig).decode()

    def verify(self, payload: bytes, signature: str) -> bool:
        """Verify *signature* against *payload* using this identity's public key."""
        try:
            sig_bytes = base64.b64decode(signature)
            self._public_key.verify(sig_bytes, payload)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_identities: dict[str, AgentIdentity] = {}


def generate_identity(agent_id: str) -> AgentIdentity:
    """Generate (or load) identity for *agent_id* and cache it."""
    if agent_id not in _identities:
        _identities[agent_id] = AgentIdentity(agent_id)
    return _identities[agent_id]


def sign_message(agent_id: str, payload: bytes) -> str:
    """Return base64 signature for *payload* signed with *agent_id*'s key."""
    identity = generate_identity(agent_id)
    return identity.sign(payload)


def verify_message(sender_pub_key_pem: str, payload: bytes, signature: str) -> bool:
    """Verify *signature* on *payload* using *sender_pub_key_pem*."""
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        pub_key = load_pem_public_key(sender_pub_key_pem.encode())
        sig_bytes = base64.b64decode(signature)
        pub_key.verify(sig_bytes, payload)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def get_all_public_keys() -> list[dict[str, str]]:
    """Return list of {agent_id, public_key_pem} for all loaded identities."""
    return [
        {"agent_id": aid, "public_key_pem": ident.public_key_pem}
        for aid, ident in _identities.items()
    ]
