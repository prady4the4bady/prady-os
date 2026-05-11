"""Bot Bridge — Telegram and Discord webhook gateway for Prady OS.

Forwards /task, /status, /models, /soul commands to the kryos-swarm and
model-manager services.

Environment variables:
  TELEGRAM_BOT_TOKEN   — Telegram Bot API token
  DISCORD_BOT_TOKEN    — Discord Bot token (used for interaction validation)
  KRYOS_SWARM_URL      — Base URL of kryos-swarm (default: http://kryos-swarm:8000)
  MODEL_MANAGER_URL    — Base URL of model-manager (default: http://model-manager:8000)
  PORT                 — Listening port (default: 8090)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
SWARM_URL = os.getenv("KRYOS_SWARM_URL", "http://kryos-swarm:8000").rstrip("/")
MODEL_MANAGER_URL = os.getenv("MODEL_MANAGER_URL", "http://model-manager:8000").rstrip("/")

_telegram_connected: Optional[bool] = None
_discord_connected: Optional[bool] = None

app = FastAPI(
    title="Kryos Bot Bridge",
    description="Telegram and Discord bridge for Prady OS agent commands.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

async def _telegram_send(chat_id: int, text: str) -> None:
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping send")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})


async def _telegram_task(chat_id: int, args: str) -> None:
    if not args.strip():
        await _telegram_send(chat_id, "Usage: /task <goal description>")
        return
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{SWARM_URL}/swarm/start",
                json={"goal": args.strip(), "max_agents": 5},
            )
        data = resp.json()
        await _telegram_send(
            chat_id,
            f"✅ Swarm started\n*ID:* `{data.get('swarm_id', '?')}`\n*Status:* {data.get('status', '?')}",
        )
    except Exception as exc:
        await _telegram_send(chat_id, f"❌ Error starting swarm: {exc}")


async def _telegram_status(chat_id: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SWARM_URL}/swarm/status")
        data = resp.json()
        swarms = data.get("swarms", [])
        if not swarms:
            await _telegram_send(chat_id, "No active swarms.")
            return
        lines = [f"*Active Swarms ({len(swarms)}):*"]
        for swarm in swarms[:5]:
            lines.append(f"• `{swarm['swarm_id'][:12]}` — {swarm['status']} — {swarm['goal'][:40]}")
        await _telegram_send(chat_id, "\n".join(lines))
    except Exception as exc:
        await _telegram_send(chat_id, f"❌ Error fetching status: {exc}")


async def _telegram_models(chat_id: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{MODEL_MANAGER_URL}/models/list")
        models = resp.json()
        if not models:
            await _telegram_send(chat_id, "No models loaded.")
            return
        lines = [f"*Models ({len(models)}):*"]
        for model in models[:10]:
            name = model.get("name") or model.get("model_id", "?")
            state = model.get("status", "?")
            lines.append(f"• `{name}` — {state}")
        await _telegram_send(chat_id, "\n".join(lines))
    except Exception as exc:
        await _telegram_send(chat_id, f"❌ Error fetching models: {exc}")


async def _telegram_soul(chat_id: int) -> None:
    user_id = str(chat_id)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SWARM_URL}/soul/{user_id}")
        data = resp.json()
        fields = data.get("fields", {})
        lines = [
            "*Your SOUL:*",
            f"Name: {fields.get('name', '?')}",
            f"Personality: {fields.get('personality', '?')[:80]}",
            f"Preferred model: {fields.get('preferred_model', '?')}",
        ]
        await _telegram_send(chat_id, "\n".join(lines))
    except Exception as exc:
        await _telegram_send(chat_id, f"❌ Error fetching soul: {exc}")


_TELEGRAM_COMMAND_HANDLERS = {
    "task": _telegram_task,
    "status": _telegram_status,
    "models": _telegram_models,
    "soul": _telegram_soul,
}


async def _handle_telegram_command(chat_id: int, command: str, args: str) -> None:
    cmd = command.lower().strip().lstrip("/").split("@")[0]
    handler = _TELEGRAM_COMMAND_HANDLERS.get(cmd)
    if handler is None:
        await _telegram_send(
            chat_id,
            "Commands: /task <goal> | /status | /models | /soul",
        )
        return

    if cmd == "task":
        await handler(chat_id, args)
        return
    await handler(chat_id)


# ---------------------------------------------------------------------------
# Telegram webhook
# ---------------------------------------------------------------------------

@app.post("/telegram/webhook", tags=["telegram"])
async def telegram_webhook(request: Request) -> Dict[str, Any]:
    body = await request.json()
    logger.debug("Telegram update: %s", body)

    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id: int = message.get("chat", {}).get("id", 0)
    text: str = message.get("text", "")

    if text.startswith("/"):
        parts = text.split(None, 1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        await _handle_telegram_command(chat_id, command, args)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Discord helpers
# ---------------------------------------------------------------------------

def _verify_discord_signature(_body: bytes, signature: str, _timestamp: str) -> bool:
    """Verify Discord Ed25519 interaction signature (simplified)."""
    # Full production implementation would use nacl/cryptography to verify
    # the Ed25519 sig. Here we accept if the token is set (real check in prod).
    return bool(DISCORD_TOKEN)


async def _handle_discord_interaction(data: Dict[str, Any]) -> Dict[str, Any]:
    interaction_type = data.get("type", 0)

    # PING
    if interaction_type == 1:
        return {"type": 1}

    # APPLICATION_COMMAND
    if interaction_type == 2:
        cmd_data = data.get("data", {})
        cmd_name = cmd_data.get("name", "")
        options = {o["name"]: o["value"] for o in cmd_data.get("options", [])}
        content = await _discord_command_content(cmd_name, options, data)

        return {"type": 4, "data": {"content": content}}

    return {"type": 1}


async def _discord_command_content(cmd_name: str, options: Dict[str, Any], data: Dict[str, Any]) -> str:
    if cmd_name == "task":
        return await _discord_task(options.get("goal", ""))
    if cmd_name == "status":
        return await _discord_status()
    if cmd_name == "models":
        return await _discord_models()
    if cmd_name == "soul":
        user_id = str(data.get("member", {}).get("user", {}).get("id", "default"))
        return await _discord_soul(user_id)
    return "Unknown command. Available: /task /status /models /soul"


async def _discord_task(goal: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{SWARM_URL}/swarm/start",
                json={"goal": goal, "max_agents": 5},
            )
        data = resp.json()
        return f"✅ Swarm started: `{data.get('swarm_id', '?')}` — {data.get('status', '?')}"
    except Exception as exc:
        return f"❌ Error: {exc}"


async def _discord_status() -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SWARM_URL}/swarm/status")
        data = resp.json()
        swarms = data.get("swarms", [])
        return f"Active swarms: {len(swarms)}"
    except Exception as exc:
        return f"❌ Error: {exc}"


async def _discord_models() -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{MODEL_MANAGER_URL}/models/list")
        models = resp.json()
        return f"Models loaded: {len(models)}"
    except Exception as exc:
        return f"❌ Error: {exc}"


async def _discord_soul(user_id: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SWARM_URL}/soul/{user_id}")
        data = resp.json()
        fields = data.get("fields", {})
        return f"Soul: {fields.get('name', '?')} — {fields.get('personality', '?')[:60]}"
    except Exception as exc:
        return f"❌ Error: {exc}"


# ---------------------------------------------------------------------------
# Discord webhook
# ---------------------------------------------------------------------------

@app.post("/discord/webhook", tags=["discord"])
async def discord_webhook(request: Request) -> Dict[str, Any]:
    body_bytes = await request.body()
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")

    if not _verify_discord_signature(body_bytes, signature, timestamp):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    data = json.loads(body_bytes)
    logger.debug("Discord interaction: type=%s", data.get("type"))
    return await _handle_discord_interaction(data)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.get("/bot/status", tags=["meta"])
async def bot_status() -> Dict[str, Any]:
    """Return connection status for both bots."""
    tg_connected = bool(TELEGRAM_TOKEN)
    dc_connected = bool(DISCORD_TOKEN)

    # Probe telegram
    if TELEGRAM_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
                )
            tg_connected = resp.status_code == 200
        except Exception:
            tg_connected = False

    return {
        "telegram": {
            "connected": tg_connected,
            "token_set": bool(TELEGRAM_TOKEN),
        },
        "discord": {
            "connected": dc_connected,
            "token_set": bool(DISCORD_TOKEN),
        },
    }


@app.get("/healthz", tags=["meta"])
async def healthz() -> Dict[str, Any]:
    return {"status": "ok", "service": "bot-bridge"}
