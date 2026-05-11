from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path


async def quantize_if_needed(model_path: Path, quantization: str | None = None) -> Path:
    quant_format = quantization or os.getenv("QUANTIZATION_FORMAT", "Q4_K_M")

    suffix = model_path.suffix.lower()
    if suffix in {".gguf", ".ggml"}:
        return model_path

    llama_quantize = shutil.which("llama-quantize") or shutil.which("quantize")
    if llama_quantize is None:
        raise RuntimeError("llama.cpp quantize binary not found in PATH")

    out_path = model_path.with_suffix(f".{quant_format}.gguf")
    proc = await asyncio.create_subprocess_exec(
        llama_quantize,
        str(model_path),
        str(out_path),
        quant_format,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"quantization failed: {stderr.decode('utf-8', errors='ignore')}")

    return out_path
