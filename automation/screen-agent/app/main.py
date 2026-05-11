"""
screen-agent FastAPI application.

Endpoints
---------
POST /actions/mouse-move       { x, y }
POST /actions/mouse-click      { x, y, button }
POST /actions/keyboard-type    { text }
POST /actions/screenshot       { label }
POST /actions/key-combo        { keys }
GET  /actions/cursor-pos       → { x, y }
POST /vision/describe-screen   { prompt }

Every mutating action (mouse, keyboard, key-combo) runs through the policy
gate before execution. See app/policy.py for details.
"""
from __future__ import annotations

import subprocess

import httpx
from fastapi import FastAPI, HTTPException

from . import actions
from .policy import PolicyDeniedError, check_policy
from .schemas import (
    ActionResponse,
    CursorPosResponse,
    DescribeScreenRequest,
    DescribeScreenResponse,
    KeyComboRequest,
    KeyboardTypeRequest,
    MouseClickRequest,
    MouseMoveRequest,
    ScreenshotRequest,
)
from .vision import describe_screen


async def _gate(action_name: str) -> None:
    """Run policy check; convert PolicyDeniedError to HTTP 403."""
    try:
        await check_policy(action_name)
    except PolicyDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _run_action(fn, *args, **kwargs) -> None:
    """Call action function and normalize subprocess/runtime failures."""
    try:
        fn(*args, **kwargs)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"xdotool error: {exc.stderr.strip() or exc}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def create_app() -> FastAPI:
    app = FastAPI(
        title="screen-agent",
        version="0.1.0",
        description="Screen automation service: mouse, keyboard, screenshot, and vision.",
    )

    # ── Mouse move ───────────────────────────────────────────────────────────

    @app.post("/actions/mouse-move", response_model=ActionResponse)
    async def mouse_move(req: MouseMoveRequest) -> ActionResponse:
        await _gate("mouse-move")
        _run_action(actions.mouse_move, req.x, req.y)
        return ActionResponse(
            success=True,
            message=f"Cursor moved to ({req.x}, {req.y})",
        )

    # ── Mouse click ──────────────────────────────────────────────────────────

    @app.post("/actions/mouse-click", response_model=ActionResponse)
    async def mouse_click(req: MouseClickRequest) -> ActionResponse:
        await _gate("mouse-click")
        _run_action(actions.mouse_click, req.x, req.y, req.button)
        return ActionResponse(
            success=True,
            message=f"{req.button.capitalize()} click at ({req.x}, {req.y})",
        )

    # ── Keyboard type ────────────────────────────────────────────────────────

    @app.post("/actions/keyboard-type", response_model=ActionResponse)
    async def keyboard_type(req: KeyboardTypeRequest) -> ActionResponse:
        await _gate("keyboard-type")
        _run_action(actions.keyboard_type, req.text)
        preview = req.text[:40] + ("…" if len(req.text) > 40 else "")
        return ActionResponse(
            success=True,
            message=f"Typed: {preview!r}",
        )

    # ── Screenshot ───────────────────────────────────────────────────────────

    @app.post("/actions/screenshot", response_model=ActionResponse)
    async def screenshot(req: ScreenshotRequest) -> ActionResponse:
        # Screenshots are observational; policy gate is not required,
        # but still honoured when policy is active.
        await _gate("screenshot")
        try:
            path = actions.take_screenshot(req.label)
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return ActionResponse(
            success=True,
            message="Screenshot saved",
            path=str(path),
        )

    # ── Key combo ────────────────────────────────────────────────────────────

    @app.post("/actions/key-combo", response_model=ActionResponse)
    async def key_combo(req: KeyComboRequest) -> ActionResponse:
        await _gate("key-combo")
        _run_action(actions.key_combo, req.keys)
        return ActionResponse(
            success=True,
            message=f"Key combo sent: {'+'.join(req.keys)}",
        )

    # ── Cursor position ──────────────────────────────────────────────────────

    @app.get("/actions/cursor-pos", response_model=CursorPosResponse)
    async def cursor_pos() -> CursorPosResponse:
        try:
            x, y = actions.cursor_pos()
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return CursorPosResponse(x=x, y=y)

    # ── Vision: describe screen ──────────────────────────────────────────────

    @app.post("/vision/describe-screen", response_model=DescribeScreenResponse)
    async def vision_describe(req: DescribeScreenRequest) -> DescribeScreenResponse:
        # 1. Take a screenshot to give the model a current view.
        try:
            screenshot_path = actions.take_screenshot("vision")
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Screenshot failed: {exc}",
            ) from exc

        # 2. Ask model-gateway to describe it.
        try:
            description = await describe_screen(screenshot_path, req.prompt)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"model-gateway error {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach model-gateway: {exc}",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return DescribeScreenResponse(
            description=description,
            screenshot_path=str(screenshot_path),
        )

    return app


app = create_app()
