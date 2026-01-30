from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    storage_root: Path
    max_concurrent_jobs: int
    demucs_default_model: str
    demucs_models: list[str]
    demucs_bin: str
    demucs_device: str
    output_format_version: str


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_settings() -> Settings:
    load_dotenv()
    base_dir = Path(__file__).resolve().parent.parent
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "20033"))
    storage_root = Path(os.getenv("STORAGE_ROOT", r"D:\demucs"))
    if not storage_root.is_absolute():
        storage_root = (base_dir / storage_root).resolve()
    max_concurrent_jobs = int(os.getenv("MAX_CONCURRENT_JOBS", "1"))
    demucs_default_model = os.getenv("DEMUCS_DEFAULT_MODEL", "htdemucs")
    demucs_models = _split_csv(
        os.getenv("DEMUCS_MODELS", "htdemucs,htdemucs_ft,mdx,mdx_q")
    )
    demucs_bin = os.getenv("DEMUCS_BIN", "demucs")
    demucs_device = os.getenv("DEMUCS_DEVICE", "cuda")
    output_format_version = os.getenv("OUTPUT_FORMAT_VERSION", "v1-wav")

    return Settings(
        host=host,
        port=port,
        storage_root=storage_root,
        max_concurrent_jobs=max_concurrent_jobs,
        demucs_default_model=demucs_default_model,
        demucs_models=demucs_models,
        demucs_bin=demucs_bin,
        demucs_device=demucs_device,
        output_format_version=output_format_version,
    )
