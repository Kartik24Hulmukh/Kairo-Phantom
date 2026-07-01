"""
kairo-sidecar/sidecar/cua/vlm_config.py

VLM (Vision-Language Model) configuration for Kairo Phantom CUA.

Hardware-adaptive model selection:
  - ≥6 GB VRAM  → Qwen2.5-VL-7B-Instruct Q4_K_M  (4.2 GB, 30-40 t/s RTX 3060)
  - 3–5 GB VRAM → Qwen2.5-VL-3B-Instruct Q4_K_M  (2.0 GB, 50+ t/s)
  - CPU-only     → Qwen2.5-VL-3B-Instruct Q4_K_M  (3-10 sec/screenshot)

Model lives at ~/.kairo-phantom/models/ and is shared across all CUA tasks.
keep_alive=0 is used after each task to free VRAM immediately.

Briefing reference:
  Doc 01 §1 — GGUF Explained / Why This Makes Kairo Lightweight
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ─── Model Registry ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VlmModelSpec:
    """Specification for a VLM model variant."""

    ollama_name: str  # Ollama model tag (for ollama pull/run)
    gguf_filename: str  # GGUF filename in model cache
    hf_repo: str  # Hugging Face repo for download
    hf_filename: str  # Hugging Face filename
    size_gb: float  # Approximate download/disk size
    min_vram_gb: float  # Minimum VRAM for GPU inference
    quant: str  # Quantization level
    description: str
    ollama_pull_tag: str = ""  # Human-readable description


# Primary model: 7B Q4_K_M — best accuracy, needs ≥6 GB VRAM
VLM_7B_Q4 = VlmModelSpec(
    ollama_name="kairo-vlm-7b",
    ollama_pull_tag="qwen2.5vl:7b",
    gguf_filename="qwen2.5-vl-7b-instruct-Q4_K_M.gguf",
    hf_repo="bartowski/Qwen2.5-VL-7B-Instruct-GGUF",
    hf_filename="Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
    size_gb=4.2,
    min_vram_gb=6.0,
    quant="Q4_K_M",
    description="Qwen2.5-VL-7B Q4_K_M — >98% accuracy vs FP16, ~30-40 t/s on RTX 3060",
)

# Fallback model: 3B Q4_K_M — lower VRAM, good for simple GUIs
VLM_3B_Q4 = VlmModelSpec(
    ollama_name="kairo-vlm-3b",
    ollama_pull_tag="qwen2.5vl:3b",
    gguf_filename="qwen2.5-vl-3b-instruct-Q4_K_M.gguf",
    hf_repo="bartowski/Qwen2.5-VL-3B-Instruct-GGUF",
    hf_filename="Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
    size_gb=2.0,
    min_vram_gb=3.0,
    quant="Q4_K_M",
    description="Qwen2.5-VL-3B Q4_K_M — good for simple GUIs, works on 8GB total RAM machines",
)


@dataclass
class VlmConfig:
    """Runtime VLM configuration — resolved once at startup."""

    selected_model: VlmModelSpec
    model_cache_dir: Path
    ollama_url: str = "http://127.0.0.1:11434"
    keep_alive: int = 0  # seconds: 0 = unload immediately after task
    context_length: int = 4096
    temperature: float = 0.0  # deterministic for grounding tasks
    max_tokens: int = 512
    gpu_available: bool = False
    vram_gb: float = 0.0
    hardware_tier: str = "cpu"  # "gpu-7b", "gpu-3b", "cpu"

    @property
    def model_path(self) -> Path:
        return self.model_cache_dir / self.selected_model.gguf_filename

    @property
    def modelfile_path(self) -> Path:
        return self.model_cache_dir / "Modelfile"

    @property
    def is_downloaded(self) -> bool:
        return self.model_path.exists() and self.model_path.stat().st_size > 100_000_000

    def to_ollama_options(self) -> dict:
        return {
            "keep_alive": self.keep_alive,
            "num_ctx": self.context_length,
            "temperature": self.temperature,
            "num_predict": self.max_tokens,
        }


# ─── Hardware Detection ───────────────────────────────────────────────────────


def _get_nvidia_vram_gb() -> float:
    """Query NVIDIA VRAM via nvidia-smi. Returns 0.0 if not available."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if lines:
                total_mb = sum(int(l.strip()) for l in lines if l.strip().isdigit())
                return total_mb / 1024.0
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0.0


def _get_amd_vram_gb() -> float:
    """Query AMD VRAM via rocm-smi or WMIC. Returns 0.0 if not available."""
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--csv"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "VRAM Total Memory (B)" in line:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        return int(parts[1].strip()) / (1024**3)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0.0


def _get_total_ram_gb() -> float:
    """Get total system RAM in GB."""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["wmic", "computersystem", "get", "TotalPhysicalMemory"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    return int(line) / (1024**3)
        else:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024**2)
    except Exception:
        pass
    return 8.0  # assume 8GB if detection fails


def detect_hardware() -> tuple[bool, float, str]:
    """
    Detect GPU availability and VRAM.

    Returns:
        (gpu_available, vram_gb, tier)
        tier: "gpu-7b", "gpu-3b", or "cpu"
    """
    nvidia_vram = _get_nvidia_vram_gb()
    amd_vram = _get_amd_vram_gb()
    vram_gb = max(nvidia_vram, amd_vram)
    gpu_available = vram_gb > 0

    if gpu_available:
        if vram_gb >= VLM_7B_Q4.min_vram_gb:
            tier = "gpu-7b"
        elif vram_gb >= VLM_3B_Q4.min_vram_gb:
            tier = "gpu-3b"
        else:
            # GPU present but not enough VRAM for even 3B — use CPU
            tier = "cpu"
    else:
        ram_gb = _get_total_ram_gb()
        # CPU inference: 3B needs ~4 GB system RAM minimum
        tier = "cpu" if ram_gb >= 4.0 else "cpu-minimal"

    return gpu_available, vram_gb, tier


def select_model(tier: str) -> VlmModelSpec:
    """Select the optimal model variant for the detected hardware tier."""
    if tier == "gpu-7b":
        return VLM_7B_Q4
    else:
        # gpu-3b, cpu, cpu-minimal → all use 3B (CPU inference is viable)
        return VLM_3B_Q4


# ─── Config Builder ───────────────────────────────────────────────────────────


def build_vlm_config(
    model_cache_dir: Optional[Path] = None,
    ollama_url: str = "http://127.0.0.1:11434",
    force_tier: Optional[str] = None,
) -> VlmConfig:
    """
    Build the VlmConfig for this machine.

    Args:
        model_cache_dir: Override model cache directory (default: ~/.kairo-phantom/models)
        ollama_url: Ollama server URL
        force_tier: Force a specific tier ("gpu-7b", "gpu-3b", "cpu") for testing

    Returns:
        Fully resolved VlmConfig
    """
    if ollama_url == "http://127.0.0.1:11434":
        env_host = os.environ.get("OLLAMA_HOST")
        if env_host:
            if not env_host.startswith("http"):
                if ":" in env_host:
                    ollama_url = f"http://{env_host}"
                else:
                    ollama_url = f"http://{env_host}:11434"
            else:
                ollama_url = env_host

    if model_cache_dir is None:
        model_cache_dir = Path.home() / ".kairo-phantom" / "models"

    model_cache_dir.mkdir(parents=True, exist_ok=True)

    gpu_available, vram_gb, detected_tier = detect_hardware()
    tier = force_tier or detected_tier
    model_spec = select_model(tier)

    return VlmConfig(
        selected_model=model_spec,
        model_cache_dir=model_cache_dir,
        ollama_url=ollama_url,
        gpu_available=gpu_available,
        vram_gb=vram_gb,
        hardware_tier=tier,
    )


# ─── Modelfile Generator ──────────────────────────────────────────────────────


def write_modelfile(config: VlmConfig) -> Path:
    """
    Write the Ollama Modelfile for kairo-vlm.

    The Modelfile references the GGUF at the model cache path, enabling
    `ollama create kairo-vlm -f Modelfile` to register it without re-downloading.
    """
    modelfile_content = f"""# Kairo Phantom VLM — Ollama Modelfile
# Generated by vlm_config.py
# Model: {config.selected_model.description}

FROM {config.model_path}

SYSTEM \"\"\"You are Kairo's vision-language screen oracle. 
You analyze screenshots of Windows applications and identify UI elements precisely.
When asked to locate elements, respond with exact coordinates in JSON format.
When asked to verify actions, respond with a confidence score and brief explanation.
Be precise, brief, and factual. Never hallucinate element positions.\"\"\"

PARAMETER temperature 0
PARAMETER num_predict 512
PARAMETER num_ctx 4096
"""
    modelfile_path = config.model_cache_dir / "Modelfile"
    modelfile_path.write_text(modelfile_content, encoding="utf-8")
    return modelfile_path


# ─── Singleton Cache ──────────────────────────────────────────────────────────

_cached_config: Optional[VlmConfig] = None


def get_vlm_config(force_refresh: bool = False) -> VlmConfig:
    """Get (or create) the singleton VLM config."""
    global _cached_config
    if _cached_config is None or force_refresh:
        _cached_config = build_vlm_config()
    return _cached_config
