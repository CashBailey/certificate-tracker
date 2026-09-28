"""
GPU auto-detection for LLM consensus parallelism.

Detects available GPU hardware at startup and determines whether the
LLM consensus pipeline should run extraction calls in parallel or
sequentially.

Rules (from High-Level Design Specification §5.1):
  - No GPU or ≤4 GB VRAM  → sequential consensus runs + sequential judge
  - >4 GB VRAM            → parallel consensus runs + sequential judge
"""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

VRAM_THRESHOLD_MB = 4096  # >4 GB enables parallel consensus


@dataclass(frozen=True)
class GpuInfo:
    """Detected GPU information."""
    detected: bool
    device_name: Optional[str] = None
    vram_total_mb: Optional[int] = None


def _detect_via_nvidia_smi() -> Optional[GpuInfo]:
    """Query nvidia-smi for GPU name and total VRAM."""
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return None

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            log.debug("nvidia-smi returned code %d", result.returncode)
            return None

        # Parse first GPU line: "NVIDIA GeForce RTX 3060, 12288"
        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            log.debug("nvidia-smi unexpected output: %s", line)
            return None

        device_name = parts[0]
        vram_mb = int(float(parts[1]))
        return GpuInfo(detected=True, device_name=device_name, vram_total_mb=vram_mb)

    except FileNotFoundError:
        return None
    except (subprocess.TimeoutExpired, ValueError, IndexError) as exc:
        log.debug("nvidia-smi detection failed: %s", exc)
        return None


def detect_gpu() -> GpuInfo:
    """Detect GPU hardware.

    Checks in order:
    1. ``GPU_VRAM_MB`` env var (manual override, useful in containers)
    2. ``nvidia-smi`` on the local system

    Returns :class:`GpuInfo` with ``detected=False`` when no GPU is found.
    """
    # 1. Environment override
    env_vram = os.getenv("GPU_VRAM_MB")
    if env_vram is not None:
        try:
            mb = int(env_vram)
            log.info("GPU VRAM override via GPU_VRAM_MB=%d MB", mb)
            return GpuInfo(
                detected=mb > 0,
                device_name="env-override",
                vram_total_mb=mb,
            )
        except ValueError:
            log.warning("Invalid GPU_VRAM_MB value: %r, falling back to auto-detect", env_vram)

    # 2. nvidia-smi
    info = _detect_via_nvidia_smi()
    if info is not None:
        log.info(
            "GPU detected: %s with %d MB VRAM",
            info.device_name, info.vram_total_mb,
        )
        return info

    log.info("No GPU detected, consensus runs will be sequential")
    return GpuInfo(detected=False)


def should_parallelize_consensus(gpu_info: Optional[GpuInfo] = None) -> bool:
    """Return True if consensus LLM runs should execute in parallel.

    Parallel mode requires >4 GB VRAM.  When *gpu_info* is ``None``,
    :func:`detect_gpu` is called automatically.
    """
    if gpu_info is None:
        gpu_info = detect_gpu()
    if not gpu_info.detected or gpu_info.vram_total_mb is None:
        return False
    return gpu_info.vram_total_mb > VRAM_THRESHOLD_MB
