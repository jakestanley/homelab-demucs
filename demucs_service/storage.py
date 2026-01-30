from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from .utils import atomic_write_json


class ArtifactStore:
    def __init__(self, storage_root: Path, output_format_version: str) -> None:
        self.storage_root = storage_root
        self.artifacts_root = storage_root / "artifacts"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.output_format_version = output_format_version

    def compute_file_hash(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def compute_signature(self, file_hash: str, mode: str, model: str) -> str:
        digest = hashlib.sha256()
        payload = f"{file_hash}:{mode}:{model}:{self.output_format_version}".encode("utf-8")
        digest.update(payload)
        return digest.hexdigest()

    def artifact_dir(self, signature: str) -> Path:
        return self.artifacts_root / signature

    def artifact_ready(self, signature: str) -> bool:
        artifact_dir = self.artifact_dir(signature)
        return (artifact_dir / "meta.json").exists() and (artifact_dir / "stems").exists()

    def ensure_artifact(self, signature: str, temp_builder) -> Path:
        artifact_dir = self.artifact_dir(signature)
        if self.artifact_ready(signature):
            return artifact_dir

        temp_dir = Path(tempfile.mkdtemp(prefix="artifact-", dir=str(self.artifacts_root)))
        try:
            temp_builder(temp_dir)
            if artifact_dir.exists():
                shutil.rmtree(artifact_dir, ignore_errors=True)
            os.replace(temp_dir, artifact_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return artifact_dir

    def write_meta(self, artifact_dir: Path, meta: dict) -> None:
        atomic_write_json(artifact_dir / "meta.json", meta)

    def copy_demucs_output(self, demucs_out_dir: Path, artifact_dir: Path) -> list[str]:
        stems_dir = artifact_dir / "stems"
        stems_dir.mkdir(parents=True, exist_ok=True)
        stems = []
        for file_path in demucs_out_dir.rglob("*.wav"):
            target = stems_dir / file_path.name
            shutil.copy2(file_path, target)
            stems.append(file_path.name)
        return sorted(set(stems))
