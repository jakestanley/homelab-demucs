from __future__ import annotations

import logging
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .job_store import JobStore
from .storage import ArtifactStore
from .utils import canonical_output_dir_name


logger = logging.getLogger(__name__)
_RATE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*seconds/s")


class WorkerManager:
    def __init__(
        self,
        job_store: JobStore,
        artifact_store: ArtifactStore,
        demucs_bin: str,
        demucs_device: str,
        max_concurrent_jobs: int,
    ) -> None:
        self.job_store = job_store
        self.artifact_store = artifact_store
        self.demucs_bin = demucs_bin
        self.demucs_device = demucs_device
        self.max_concurrent_jobs = max(1, max_concurrent_jobs)
        self._lock = threading.Lock()
        self._paused = False
        self._running_jobs: dict[str, threading.Thread] = {}
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def status(self) -> dict:
        with self._lock:
            return {
                "paused": self._paused,
                "running_jobs": list(self._running_jobs.keys()),
            }

    def _run_loop(self) -> None:
        while True:
            time.sleep(0.5)
            with self._lock:
                paused = self._paused
                running = len(self._running_jobs)
            if paused or running >= self.max_concurrent_jobs:
                continue
            queued = self.job_store.list_jobs(status="queued", limit=1)
            if not queued:
                continue
            job = queued[0]
            thread = threading.Thread(target=self._process_job, args=(job["id"],), daemon=True)
            with self._lock:
                self._running_jobs[job["id"]] = thread
            thread.start()

    def _process_job(self, job_id: str) -> None:
        try:
            self.job_store.set_status(job_id, "running", message="Running")
            self.job_store.update_progress(job_id, step="processing", message="Processing inputs")
            job = self.job_store.get_job(job_id)
            if not job:
                return
            mode = job["input"]["mode"]
            model = job["input"]["model"]
            files = job["input"]["files"]
            output_entries = []
            had_errors = False
            for file_entry in files:
                stored_name = file_entry["stored_name"]
                input_path = self.job_store.job_input_dir(job_id) / stored_name
                file_hash = file_entry["sha256"]
                modes = self._expand_modes(mode)
                file_results = []
                input_index = int(file_entry.get("input_index") or 0)
                output_dir_name = canonical_output_dir_name(file_entry["name"])
                try:
                    for mode_entry in modes:
                        signature = self.artifact_store.compute_signature(
                            file_hash=file_hash, mode=mode_entry, model=model
                        )
                        cache_hit = self.artifact_store.artifact_ready(signature)
                        if cache_hit:
                            cached_metrics = self._artifact_metrics(signature)
                            output_entries.append(
                                {
                                    "file": file_entry["name"],
                                    "stored_name": stored_name,
                                    "input_index": input_index,
                                    "output_dir_name": output_dir_name,
                                    "mode": mode_entry,
                                    "signature": signature,
                                    "cache_hit": True,
                                    **cached_metrics,
                                }
                            )
                            file_results.append(
                                {
                                    "mode": mode_entry,
                                    "signature": signature,
                                    "cache_hit": True,
                                    **cached_metrics,
                                }
                            )
                            continue
                        run_metrics = self._run_demucs(
                            job_id, input_path, mode_entry, model, signature
                        )
                        output_entries.append(
                            {
                                "file": file_entry["name"],
                                "stored_name": stored_name,
                                "input_index": input_index,
                                "output_dir_name": output_dir_name,
                                "mode": mode_entry,
                                "signature": signature,
                                "cache_hit": False,
                                **run_metrics,
                            }
                        )
                        file_results.append(
                            {
                                "mode": mode_entry,
                                "signature": signature,
                                "cache_hit": False,
                                **run_metrics,
                            }
                        )
                    self.job_store.update_progress(
                        job_id, processed_inc=1, message=f"Processed {file_entry['name']}"
                    )
                except Exception as exc:
                    had_errors = True
                    file_results.append({"error": str(exc)})
                    self.job_store.update_progress(
                        job_id, errors_inc=1, message=f"Failed {file_entry['name']}"
                    )
                finally:
                    self._record_file_results(job_id, stored_name, file_results)

            zip_path, manifest = self._build_output_zip(job_id, output_entries)
            size_bytes = zip_path.stat().st_size
            job_signature = self._job_signature(output_entries)
            self.job_store.set_output(
                job_id,
                artifact_name=zip_path.name,
                content_type="application/zip",
                size_bytes=size_bytes,
                signature=job_signature,
                manifest=manifest,
            )
            if had_errors:
                self.job_store.set_status(job_id, "failed", message="Completed with errors")
            else:
                self.job_store.set_status(job_id, "succeeded", message="Complete")
        except Exception as exc:
            self.job_store.set_status(job_id, "failed", message="Failed", error=str(exc))
        finally:
            with self._lock:
                self._running_jobs.pop(job_id, None)

    def _record_file_results(self, job_id: str, stored_name: str, results: list[dict]) -> None:
        def updater(job: dict) -> dict:
            for entry in job.get("input", {}).get("files", []):
                if entry.get("stored_name") == stored_name:
                    entry["results"] = results
            return job

        self.job_store.update_job(job_id, updater)

    def _expand_modes(self, mode: str) -> list[str]:
        if mode == "both":
            return ["4", "2"]
        return [mode]

    def _run_demucs(
        self, job_id: str, input_path: Path, mode: str, model: str, signature: str
    ) -> dict:
        def builder(temp_dir: Path) -> None:
            out_dir = temp_dir / "demucs"
            out_dir.mkdir(parents=True, exist_ok=True)
            cmd = [self.demucs_bin, "-n", model, "--out", str(out_dir)]
            if self.demucs_device:
                cmd.extend(["--device", self.demucs_device])
            if mode == "2":
                cmd.extend(["--two-stems", "vocals"])
            cmd.append(str(input_path))
            logger.info("job=%s running demucs command: %s", job_id, " ".join(cmd))
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if result.stdout:
                for line in result.stdout.splitlines():
                    logger.info("job=%s demucs: %s", job_id, line)
            if result.stderr:
                for line in result.stderr.splitlines():
                    logger.warning("job=%s demucs: %s", job_id, line)
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
                details = " | ".join(tail) if tail else f"exit code {result.returncode}"
                raise RuntimeError(f"Demucs failed for {input_path.name}: {details}")
            rate = self._extract_processing_rate(result.stdout, result.stderr)
            stems = self.artifact_store.copy_demucs_output(out_dir, temp_dir)
            meta = {
                "input_name": input_path.name,
                "mode": mode,
                "model": model,
                "signature": signature,
                "stems": stems,
            }
            if rate is not None:
                meta["rate_seconds_per_second"] = rate
            self.artifact_store.write_meta(
                temp_dir,
                meta,
            )

        self.artifact_store.ensure_artifact(signature, builder)
        return self._artifact_metrics(signature)

    def _extract_processing_rate(self, stdout: str | None, stderr: str | None) -> float | None:
        matches = _RATE_RE.findall(f"{stdout or ''}\n{stderr or ''}")
        if not matches:
            return None
        return float(matches[-1])

    def _artifact_metrics(self, signature: str) -> dict:
        meta_path = self.artifact_store.artifact_dir(signature) / "meta.json"
        if not meta_path.exists():
            return {}
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        rate = meta.get("rate_seconds_per_second")
        if isinstance(rate, (int, float)):
            return {"rate_seconds_per_second": float(rate)}
        return {}

    def _build_output_zip(self, job_id: str, output_entries: list[dict]) -> tuple[Path, dict]:
        import zipfile

        job = self.job_store.get_job(job_id)
        if not job:
            raise RuntimeError("Job missing for output packaging.")

        manifest = self._build_manifest(job_id, output_entries)

        output_zip_path = self.job_store.job_output_zip_path(job_id)
        output_zip_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".zip", dir=str(output_zip_path.parent)
        ) as handle:
            temp_zip = Path(handle.name)
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
            for entry in output_entries:
                signature = entry["signature"]
                file_name = entry["output_dir_name"]
                mode = entry["mode"]
                artifact_dir = self.artifact_store.artifact_dir(signature)
                stems_dir = artifact_dir / "stems"
                for stem_path in sorted(stems_dir.glob("*.wav"), key=lambda item: item.name):
                    archive_name = f"{job_id}/{file_name}/{mode}/{stem_path.name}"
                    zip_handle.write(stem_path, archive_name)
            zip_handle.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        os.replace(temp_zip, output_zip_path)
        return output_zip_path, manifest

    def _job_signature(self, output_entries: list[dict]) -> str:
        import hashlib

        digest = hashlib.sha256()
        for entry in sorted(
            output_entries,
            key=lambda item: (
                item.get("stored_name", item["file"]),
                item["mode"],
                item["signature"],
            ),
        ):
            digest.update(f"{entry['file']}:{entry['mode']}:{entry['signature']}".encode("utf-8"))
        return digest.hexdigest()

    def _build_manifest(self, job_id: str, output_entries: list[dict]) -> dict:
        files: dict[str, dict] = {}
        for entry in output_entries:
            stored_name = entry.get("stored_name", entry["file"])
            file_doc = files.setdefault(
                stored_name,
                {
                    "input_index": entry.get("input_index"),
                    "input_stored_name": stored_name,
                    "input_original_name": entry["file"],
                    "output_dir_name": entry["output_dir_name"],
                    "output_dir_path": f"{job_id}/{entry['output_dir_name']}",
                    "modes": [],
                },
            )
            mode_doc = {
                "mode": entry["mode"],
                "signature": entry["signature"],
                "cache_hit": bool(entry.get("cache_hit")),
                "stems": self._artifact_stems(entry["signature"]),
            }
            rate = entry.get("rate_seconds_per_second")
            if isinstance(rate, (int, float)):
                mode_doc["rate_seconds_per_second"] = float(rate)
            file_doc["modes"].append(mode_doc)

        sorted_files = sorted(
            files.values(),
            key=lambda item: (
                int(item.get("input_index") or 0),
                item.get("input_stored_name") or "",
            ),
        )
        for file_doc in sorted_files:
            file_doc["modes"].sort(key=lambda item: item["mode"])

        return {
            "version": "v1",
            "job_id": job_id,
            "files": sorted_files,
        }

    def _artifact_stems(self, signature: str) -> list[str]:
        meta_path = self.artifact_store.artifact_dir(signature) / "meta.json"
        if not meta_path.exists():
            return []
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        stems = meta.get("stems")
        if isinstance(stems, list):
            valid = [name for name in stems if isinstance(name, str)]
            return sorted(valid)
        return []
